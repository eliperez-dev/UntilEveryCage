"""Bounded normal-browser acquisition for APHIS Public Search Tool exports.

The APHIS site is a public UI.  This module deliberately drives only the
documented profile page and its visible CSV export control using a fresh,
headless Firefox profile.  It does not discover private endpoints, reuse a
profile, solve challenges, or interact with authentication controls.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from pipeline.common.acquisition import AcquisitionError, utc_now
from pipeline.contracts.source_lifecycle import atomic_json
from pipeline.sources.us.fsis.firefox_acquisition import _complete_download, _open_driver, _remove_downloads
from .capture import build_capture_manifest


def _visible_export_control(driver: Any, by: Any) -> Any | None:
    for control in driver.find_elements(by.CSS_SELECTOR, "button, a, [role='button']"):
        try:
            label = " ".join(
                str(control.get_attribute("aria-label") or control.get_attribute("title") or control.text or "").split()
            )
            if control.is_displayed() and control.is_enabled() and "export" in label.casefold() and "csv" in label.casefold():
                return control
        except Exception:
            continue
    return None


def _visible_search_control(driver: Any, by: Any) -> Any | None:
    for control in driver.find_elements(by.CSS_SELECTOR, "button, [role='button']"):
        try:
            label = " ".join(str(control.get_attribute("aria-label") or control.text or "").split())
            if control.is_displayed() and control.is_enabled() and label.casefold() == "search":
                return control
        except Exception:
            continue
    return None


def _visible_profile_link(driver: Any, by: Any, profile: str) -> Any | None:
    expected = "view annual reports" if profile == "annual_reports" else "view inspection reports"
    for link in driver.find_elements(by.CSS_SELECTOR, "a"):
        try:
            label = " ".join(str(link.text or link.get_attribute("aria-label") or "").split()).casefold()
            if link.is_displayed() and link.is_enabled() and label == expected:
                return link
        except Exception:
            continue
    return None


def _visible_next_page(driver: Any, by: Any) -> Any | None:
    for control in driver.find_elements(by.CSS_SELECTOR, "button, [role='button']"):
        try:
            label = " ".join(str(control.get_attribute("aria-label") or control.get_attribute("title") or control.text or "").split())
            if control.is_displayed() and control.is_enabled() and label in {">", "Next", "Next Page"}:
                return control
        except Exception:
            continue
    return None


def _select_exact_option(driver: Any, by: Any, *, value: str, label: str) -> bool:
    """Select one visible HTML ``select`` option, without guessing a field."""
    for element in driver.find_elements(by.CSS_SELECTOR, "select"):
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            options = element.find_elements(by.CSS_SELECTOR, "option")
            matching = [option for option in options if str(option.text).strip() == value]
            if len(matching) != 1:
                continue
            driver.execute_script("arguments[0].value=arguments[1];arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", element, matching[0].get_attribute("value"))
            return True
        except Exception:
            continue
    return False


def acquire_public_search_export(
    *, profile: str, profile_url: str, output_root: str | Path, run_id: str,
    query_context: dict[str, Any], artifact_validator: Callable[[Path, dict[str, str]], None],
    max_attempts: int = 2, max_bytes: int = 128 * 1024 * 1024,
    navigation_timeout_seconds: float = 60.0, download_timeout_seconds: float = 90.0,
    driver_opener: Callable[[Path], tuple[Any, dict[str, Any]]] = _open_driver,
) -> dict[str, Any]:
    if profile not in {"annual_reports", "inspections"}:
        raise AcquisitionError("browser acquisition supports annual_reports or inspections only", failure_class="configuration")
    if not 1 <= max_attempts <= 3:
        raise AcquisitionError("browser max_attempts must be between 1 and 3", failure_class="configuration")
    if max_bytes <= 0 or navigation_timeout_seconds <= 0 or download_timeout_seconds <= 0:
        raise AcquisitionError("browser acquisition bounds must be positive", failure_class="configuration")
    if profile == "annual_reports" and not str(query_context.get("selected_year") or "").strip():
        raise AcquisitionError("annual report browser acquisition requires query_context.selected_year", failure_class="configuration")
    page_limit = int(query_context.get("max_pages") or 1)
    if not 1 <= page_limit <= 200:
        raise AcquisitionError("query_context.max_pages must be between 1 and 200", failure_class="configuration")

    run_dir = Path(output_root) / "us.aphis" / run_id
    artifact_path = run_dir / f"{profile}.csv"
    attempts: list[dict[str, Any]] = []
    requested_at = utc_now()
    for attempt in range(1, max_attempts + 1):
        download_dir = Path(tempfile.mkdtemp(prefix="aphis-firefox-"))
        driver = None
        try:
            driver, runtime = driver_opener(download_dir)
            driver.set_page_load_timeout(navigation_timeout_seconds)
            driver.get(profile_url)
            by = runtime.get("by")
            if by is None:
                raise AcquisitionError("browser runtime lacks DOM selector support", failure_class="browser-runtime")
            selected_year = str(query_context.get("selected_year") or "").strip()
            if selected_year and not _select_exact_option(driver, by, value=selected_year, label="selected_year"):
                raise AcquisitionError("documented APHIS year selector was not found", failure_class="source-ui-control-not-found", action="verify the visible annual-report year control")
            selected_scope = str(query_context.get("selected_scope") or "").strip()
            if profile == "inspections" and not _select_exact_option(driver, by, value=selected_scope, label="selected_scope"):
                raise AcquisitionError("documented APHIS inspection scope selector was not found", failure_class="source-ui-control-not-found", action="verify the visible inspection scope control")
            search = _visible_search_control(driver, by)
            if search is None:
                raise AcquisitionError("documented APHIS Search control was not found", failure_class="source-ui-control-not-found", action="verify the public profile search control")
            search.click()
            # The Public Search Tool first shows matching registrants; choose
            # the visible profile-specific results link before exporting.
            profile_deadline = time.monotonic() + min(30.0, navigation_timeout_seconds)
            profile_link = None
            while time.monotonic() < profile_deadline:
                profile_link = _visible_profile_link(driver, by, profile)
                if profile_link is not None:
                    break
                time.sleep(0.5)
            if profile_link is None:
                raise AcquisitionError("documented APHIS profile results link was not found", failure_class="source-ui-control-not-found", action="verify the visible profile results link")
            profile_link.click()
            page_dir = run_dir / "pages"
            page_dir.mkdir(parents=True, exist_ok=True)
            pages: list[Path] = []
            for ordinal in range(1, page_limit + 1):
                deadline = time.monotonic() + min(30.0, navigation_timeout_seconds)
                control = None
                while time.monotonic() < deadline:
                    control = _visible_export_control(driver, by)
                    if control is not None:
                        break
                    time.sleep(0.5)
                if control is None:
                    raise AcquisitionError("documented APHIS Export to CSV control was not found", failure_class="source-ui-control-not-found", action="verify the public profile page and visible export control")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", control)
                control.click()
                deadline = time.monotonic() + download_timeout_seconds
                downloaded = None
                while time.monotonic() < deadline:
                    downloaded = _complete_download(download_dir, max_bytes=max_bytes)
                    if downloaded is not None:
                        break
                    time.sleep(0.5)
                if downloaded is None:
                    raise AcquisitionError("APHIS browser export did not produce one complete CSV", failure_class="browser-download-timeout", retryable=True, action="inspect the normal public export control")
                artifact_validator(downloaded, {})
                page_path = page_dir / f"page-{ordinal:03d}.csv"
                shutil.copy2(downloaded, page_path)
                pages.append(page_path)
                downloaded.unlink(missing_ok=True)
                if ordinal < page_limit:
                    next_page = _visible_next_page(driver, by)
                    if next_page is None:
                        raise AcquisitionError("APHIS paginator ended before requested page bound", failure_class="pagination-boundary", action="record bounded coverage; do not infer missing rows")
                    next_page.click()
                    time.sleep(1.0)
            capture = build_capture_manifest(pages, output_path=run_dir / "capture-manifest.json", source_url=profile_url, retrieved_at_utc=utc_now(), query_context={**query_context, "profile": profile}, lineage_output_path=artifact_path, profile=profile)
            digest = str(capture["derived_artifact"]["sha256"])
            attempts.append({"attempt": attempt, "outcome": "success", "artifact_verified": True})
            metadata = {
                "acquisition_method": "firefox_public_ui_export", "source_id": "us.aphis", "profile": profile,
                "artifact": artifact_path.name, "artifact_path": str(artifact_path), "run_id": run_id,
                "requested_url": profile_url, "final_url": profile_url, "requested_at_utc": requested_at,
                "retrieved_at_utc": utc_now(), "sha256": digest, "byte_size": artifact_path.stat().st_size,
                "query_context": {**query_context, "profile": profile}, "attempts": attempts,
                "browser": {key: value for key, value in runtime.items() if key not in {"timeout_exception", "by"}},
                "retention": {"class": "restricted-research-evidence", "public_exposure": False, "review_required": True},
            }
            atomic_json(run_dir / "acquisition-metadata.json", metadata)
            return metadata
        except AcquisitionError as error:
            attempts.append({"attempt": attempt, "outcome": "failed", "failure_class": error.failure_class, "retryable": error.retryable})
            if attempt == max_attempts or not error.retryable:
                run_dir.mkdir(parents=True, exist_ok=True)
                atomic_json(run_dir / "acquisition-failure.json", {"schema_version": "acquisition-failure-v1", "source_id": "us.aphis", "profile": profile, "run_id": run_id, "failure_class": error.failure_class, "retryable": error.retryable, "action": error.action, "attempts": attempts, "artifact_created": False, "public_exposure": False})
                raise
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            _remove_downloads(download_dir)
            shutil.rmtree(download_dir, ignore_errors=True)
    raise AcquisitionError("APHIS browser acquisition retry loop did not complete", failure_class="runtime")
