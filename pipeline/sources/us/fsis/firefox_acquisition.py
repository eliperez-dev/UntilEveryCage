"""Bounded Firefox download acquisition for the private FSIS refresh.

This is an explicit source method, not a stealth or anti-bot framework.  Each
attempt uses a fresh temporary Firefox profile and a caller-selected private
download directory.  Browser navigation timeouts are tolerated only when a
complete downloaded file passes size and source-schema validation.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from pipeline.common.acquisition import AcquisitionError, require_terms_review, utc_now
from pipeline.contracts.source_lifecycle import atomic_json


def _load_selenium() -> Any:
    try:
        import selenium
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.common.by import By
    except ImportError as error:
        raise AcquisitionError(
            "Firefox acquisition requires the optional Selenium package and an installed Firefox browser",
            failure_class="configuration",
            action="install the documented Firefox/Selenium runtime, then rerun with --acquisition-method firefox",
        ) from error
    return {"selenium": selenium, "webdriver": webdriver, "TimeoutException": TimeoutException, "By": By}


def _open_driver(download_dir: Path) -> tuple[Any, dict[str, Any]]:
    runtime = _load_selenium()
    options = runtime["webdriver"].FirefoxOptions()
    options.add_argument("-headless")
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.dir", str(download_dir))
    options.set_preference("browser.download.useDownloadDir", True)
    options.set_preference("browser.download.alwaysOpenPanel", False)
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "text/csv,application/csv,application/octet-stream")
    options.set_preference("pdfjs.disabled", True)
    # Do not set options.profile: Selenium creates a fresh disposable profile.
    driver = runtime["webdriver"].Firefox(options=options)
    capabilities = getattr(driver, "capabilities", {}) or {}
    return driver, {
        "browser": "Firefox",
        "browser_version": capabilities.get("browserVersion", "unknown"),
        "selenium_version": getattr(runtime["selenium"], "__version__", "unknown"),
        "profile": "fresh-temporary",
        "headless": True,
        "timeout_exception": runtime["TimeoutException"],
        "by": runtime["By"],
    }


def _complete_download(download_dir: Path, *, max_bytes: int) -> Path | None:
    partials = [path for path in download_dir.iterdir() if path.is_file() and path.name.endswith(".part")]
    complete = [path for path in download_dir.iterdir() if path.is_file() and not path.name.endswith(".part")]
    if partials or len(complete) != 1:
        return None
    path = complete[0]
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise AcquisitionError(
            f"Firefox download size {size} is outside the allowed bound",
            failure_class="browser-download-size",
            action="inspect the private browser attempt and source edition",
        )
    return path


def _remove_downloads(download_dir: Path) -> None:
    try:
        paths = tuple(download_dir.iterdir())
    except OSError:
        return
    for path in paths:
        if path.is_file():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # Cleanup must never mask the authoritative acquisition or
                # validation failure. The private failure ledger remains the
                # source of truth for the attempt outcome.
                continue


def _validate_acquisition_authorization(value: dict[str, Any] | None, *, source_id: str, url: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("status") != "authorized":
        raise AcquisitionError(
            "Firefox acquisition requires an explicit owner acquisition-authorization record",
            failure_class="authorization",
            action="provide a scoped authorization record; keep redistribution terms and publication blocked until separately reviewed",
        )
    for field in ("basis", "scope"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise AcquisitionError(
                f"acquisition authorization requires a non-empty {field}",
                failure_class="authorization",
                action="provide a scoped authorization record with owner basis and source scope",
            )
    restrictions = value.get("restrictions")
    if not isinstance(restrictions, list) or not restrictions or not all(isinstance(item, str) and item.strip() for item in restrictions):
        raise AcquisitionError(
            "acquisition authorization restrictions must be a non-empty list of strings",
            failure_class="authorization",
            action="provide typed private/no-public restrictions in the authorization record",
        )
    allowed_routes = value.get("allowed_routes")
    if not isinstance(allowed_routes, list) or not all(
        isinstance(item, dict)
        and all(isinstance(item.get(field), str) and item[field].strip() for field in ("source_id", "role", "url"))
        for item in allowed_routes
    ):
        raise AcquisitionError(
            "acquisition authorization requires typed allowed_routes entries",
            failure_class="authorization",
            action="bind authorization to exact FSIS source IDs and official URLs",
        )
    expected_role = "demographics" if source_id.endswith(".demographics") else "directory"
    if not any(item["source_id"] == source_id and item["role"] == expected_role and item["url"] == url for item in allowed_routes):
        raise AcquisitionError(
            f"acquisition authorization does not cover {source_id} at the configured official URL",
            failure_class="authorization",
            action="add the exact approved FSIS route to the private authorization record",
        )
    terms_status = value.get("terms_status", "unknown")
    if terms_status not in {"unknown", "pending_review"}:
        raise AcquisitionError(
            "Firefox acquisition authorization cannot claim redistribution terms approval",
            failure_class="authorization",
            action="record terms as unknown or pending_review; publication remains blocked",
        )
    return {
        "status": "authorized",
        "basis": value["basis"],
        "scope": value["scope"],
        "restrictions": restrictions,
        "allowed_routes": allowed_routes,
        "recorded_at_utc": value.get("recorded_at_utc"),
        "terms_status": terms_status,
        "publication_status": "not_eligible",
    }


def acquire_firefox(
    *,
    source_id: str,
    page_url: str,
    url: str,
    output_root: str | Path,
    artifact_name: str,
    terms_review_path: str | Path | None,
    acquisition_authorization: dict[str, Any] | None,
    run_id: str | None = None,
    max_attempts: int = 2,
    max_bytes: int = 128 * 1024 * 1024,
    navigation_timeout_seconds: float = 60.0,
    download_timeout_seconds: float = 90.0,
    effective_date: str | None = None,
    publication_date: str | None = None,
    code_version: str = "unknown",
    config_version: str = "unknown",
    coverage: str | None = None,
    rights_caveat: str | None = None,
    privacy_caveat: str | None = None,
    artifact_validator: Callable[[Path, dict[str, str]], None] | None = None,
    driver_opener: Callable[[Path], tuple[Any, dict[str, Any]]] = _open_driver,
) -> dict[str, Any]:
    if not source_id or not page_url or not url or not artifact_name:
        raise AcquisitionError("source_id, page_url, url, and artifact_name are required", failure_class="configuration")
    if max_bytes <= 0 or navigation_timeout_seconds <= 0 or download_timeout_seconds <= 0:
        raise AcquisitionError("Firefox acquisition bounds must be positive", failure_class="configuration")
    if not 1 <= max_attempts <= 3:
        raise AcquisitionError("Firefox max_attempts must be between 1 and 3", failure_class="configuration")
    authorization = _validate_acquisition_authorization(acquisition_authorization, source_id=source_id, url=url)
    terms_review = require_terms_review(Path(terms_review_path)) if terms_review_path is not None else {
        "status": "unknown",
        "required_before_publication": True,
    }
    run_id = run_id or (utc_now().replace(":", "").replace("-", "") + "-" + uuid.uuid4().hex[:8])
    run_dir = Path(output_root) / source_id / run_id
    artifact_path = run_dir / artifact_name
    attempts: list[dict[str, Any]] = []
    requested_at = utc_now()
    last_runtime: dict[str, Any] = {}

    for attempt_number in range(1, max_attempts + 1):
        attempt_dir = run_dir / "browser-attempts" / f"attempt-{attempt_number}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        # Keep the transient browser download path short.  Firefox on Windows
        # can silently fail to complete a download when the private run path
        # is deeply nested near the legacy MAX_PATH boundary.
        download_dir = Path(tempfile.mkdtemp(prefix="fsis-firefox-"))
        driver = None
        navigation_mode = "direct-official-url"
        timeout_after_download_start = False
        try:
            driver, runtime = driver_opener(download_dir)
            last_runtime = runtime
            driver.set_page_load_timeout(navigation_timeout_seconds)
            driver.get(page_url)
            by = runtime.get("by")
            if by is not None:
                link_deadline = time.monotonic() + min(30.0, navigation_timeout_seconds)
                while time.monotonic() < link_deadline:
                    if any(link.get_attribute("href") == url for link in driver.find_elements(by.CSS_SELECTOR, "a[href]")):
                        break
                    time.sleep(0.5)
                for control in driver.find_elements(by.CSS_SELECTOR, "button, summary, [role='button']"):
                    label = " ".join(control.text.split())
                    if "Active Establishment MPI Data Files and Other References" in label and control.is_displayed() and control.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", control)
                        control.send_keys("\ue007")
                        time.sleep(2)
                        break
            # The configured official URL is the observed public download
            # route. Navigate to it directly after the landing-page check so
            # duplicate/collapsed links cannot change the selected artifact.
            try:
                driver.get(url)
            except runtime["timeout_exception"]:
                timeout_after_download_start = True
            deadline = time.monotonic() + download_timeout_seconds
            downloaded = None
            while time.monotonic() < deadline:
                downloaded = _complete_download(download_dir, max_bytes=max_bytes)
                if downloaded is not None:
                    break
                time.sleep(0.5)
            if downloaded is None:
                observed_files = []
                for path in sorted(download_dir.iterdir()):
                    if path.is_file():
                        observed_files.append({"name": path.name, "byte_size": path.stat().st_size})
                raise AcquisitionError(
                    "Firefox did not produce one complete CSV download before the bounded timeout",
                    failure_class="browser-download-timeout",
                    retryable=True,
                    action="inspect the private browser attempt or use the authorized operator capture route",
                )
            raw_size = downloaded.stat().st_size
            digest = hashlib.sha256(downloaded.read_bytes()).hexdigest()
            if artifact_validator is not None:
                artifact_validator(downloaded, {})
            if artifact_path.exists():
                existing_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                if existing_digest != digest:
                    raise AcquisitionError("existing browser artifact differs from newly acquired bytes", failure_class="artifact-collision", action="use a new run id and preserve both observations")
            else:
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(downloaded, artifact_path)
            attempts.append({
                "attempt": attempt_number,
                "outcome": "success",
                "navigation_mode": navigation_mode,
                "navigation_timeout_after_download_start": timeout_after_download_start,
                "artifact_verified": True,
            })
            metadata = {
                "acquisition_method": "firefox_browser_download",
                "method_choice": "firefox",
                "source_id": source_id,
                "artifact": artifact_name,
                "artifact_path": str(artifact_path),
                "run_id": run_id,
                "requested_url": url,
                "final_url": url,
                "page_url": page_url,
                "requested_at_utc": requested_at,
                "retrieved_at_utc": utc_now(),
                "effective_date": effective_date or "unknown",
                "publication_date": publication_date,
                "sha256": digest,
                "byte_size": raw_size,
                "code_version": code_version,
                "config_version": config_version,
                "coverage": coverage,
                "rights_caveat": rights_caveat,
                "privacy_caveat": privacy_caveat,
                "terms_review": terms_review,
                "acquisition_authorization": authorization,
                "attempts": attempts,
                "browser": {key: value for key, value in last_runtime.items() if key not in {"timeout_exception", "by"}},
                "navigation_mode": navigation_mode,
                "navigation_timeout_after_download_start": timeout_after_download_start,
                "retention": {"class": "restricted-research-evidence", "public_exposure": False, "review_required": True},
            }
            atomic_json(run_dir / "acquisition-metadata.json", metadata)
            return metadata
        except AcquisitionError as error:
            attempt_record = {"attempt": attempt_number, "outcome": "failed", "failure_class": error.failure_class, "retryable": error.retryable, "navigation_mode": navigation_mode}
            if error.failure_class == "browser-download-timeout":
                attempt_record["observed_files"] = locals().get("observed_files", [])
            attempts.append(attempt_record)
            if attempt_number == max_attempts or not error.retryable:
                atomic_json(run_dir / "acquisition-failure.json", {
                    "schema_version": "acquisition-failure-v1",
                    "source_id": source_id,
                    "run_id": run_id,
                    "failure_class": error.failure_class,
                    "retryable": error.retryable,
                    "error": str(error),
                    "action": error.action,
                    "attempts": attempts,
                    "artifact_created": False,
                    "public_exposure": False,
                })
                raise
        except Exception as error:
            safe_error = AcquisitionError(
                f"Firefox acquisition failed: {type(error).__name__}",
                failure_class="browser-runtime",
                retryable=False,
                action="inspect the private browser attempt and runtime setup",
            )
            atomic_json(run_dir / "acquisition-failure.json", {
                "schema_version": "acquisition-failure-v1", "source_id": source_id, "run_id": run_id,
                "failure_class": safe_error.failure_class, "retryable": False, "error": str(safe_error),
                "action": safe_error.action, "attempts": attempts, "artifact_created": False, "public_exposure": False,
            })
            raise safe_error from error
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            if not any(item.get("outcome") == "success" and item.get("attempt") == attempt_number for item in attempts):
                _remove_downloads(download_dir)
            shutil.rmtree(download_dir, ignore_errors=True)
    raise AcquisitionError("Firefox acquisition retry loop did not complete", failure_class="runtime")
