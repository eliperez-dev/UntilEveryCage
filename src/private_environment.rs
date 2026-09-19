//! Fail-closed checks for the private production-shaped runtime.
//!
//! The restriction ledger and restore snapshot are deliberately separate JSON
//! control-plane inputs. They contain opaque source keys only; they must never
//! contain addresses, coordinates, requester contact details, or source text.

use ipnet::IpNet;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs;
use std::net::IpAddr;
use std::path::Path;
use std::str::FromStr;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProxyConfig {
    pub trust_forwarded_for: bool,
    pub trusted_proxy_cidrs: Vec<IpNet>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq, Hash)]
pub struct RestrictionReference {
    pub source_id: String,
    pub source_record_key: String,
    pub scope: String,
    pub action: String,
}

#[derive(Debug, Deserialize)]
struct RestrictionLedger {
    schema_version: u64,
    revision: String,
    ledger_sha256: String,
    active_restrictions: Vec<RestrictionReference>,
}

#[derive(Debug, Deserialize)]
struct RestrictionSnapshot {
    ledger_revision: String,
    ledger_sha256: String,
    active_restrictions: Vec<RestrictionReference>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StartupGateReport {
    pub restriction_ledger: &'static str,
    pub release_manifest: &'static str,
}

fn canonical_json(value: &Value) -> String {
    match value {
        Value::Object(map) => {
            let mut keys: Vec<_> = map.keys().collect();
            keys.sort();
            format!(
                "{{{}}}",
                keys.into_iter()
                    .map(|key| format!(
                        "{}:{}",
                        serde_json::to_string(key).expect("JSON key serialization"),
                        canonical_json(&map[key])
                    ))
                    .collect::<Vec<_>>()
                    .join(",")
            )
        }
        Value::Array(items) => format!(
            "[{}]",
            items
                .iter()
                .map(canonical_json)
                .collect::<Vec<_>>()
                .join(",")
        ),
        _ => value.to_string(),
    }
}

fn ledger_digest(ledger: &RestrictionLedger) -> String {
    let payload = json!({
        "schema_version": ledger.schema_version,
        "revision": ledger.revision,
        "active_restrictions": ledger.active_restrictions,
    });
    format!("{:x}", Sha256::digest(canonical_json(&payload).as_bytes()))
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path, label: &str) -> Result<T, String> {
    let bytes = fs::read(path).map_err(|_| format!("{label} is unavailable"))?;
    serde_json::from_slice(&bytes).map_err(|_| format!("{label} is invalid"))
}

fn verify_ledger(ledger_path: &Path, snapshot_path: &Path) -> Result<(), String> {
    if ledger_path == snapshot_path {
        return Err("restriction ledger and restored snapshot must be separate files".into());
    }
    let ledger: RestrictionLedger = read_json(ledger_path, "restriction ledger")?;
    if ledger.schema_version != 1 || ledger.revision.trim().is_empty() {
        return Err("restriction ledger schema or revision is unsupported".into());
    }
    if ledger.ledger_sha256 != ledger_digest(&ledger) {
        return Err("restriction ledger digest is invalid".into());
    }
    if ledger.active_restrictions.iter().any(|reference| {
        reference.source_id.trim().is_empty()
            || reference.source_record_key.trim().is_empty()
            || reference.scope.trim().is_empty()
            || reference.action != "suppress"
    }) {
        return Err("restriction ledger references are invalid".into());
    }
    let snapshot: RestrictionSnapshot = read_json(snapshot_path, "restored restriction snapshot")?;
    if snapshot.ledger_revision != ledger.revision || snapshot.ledger_sha256 != ledger.ledger_sha256
    {
        return Err("restored restriction state is stale".into());
    }
    let expected: HashSet<_> = ledger.active_restrictions.iter().collect();
    let applied: HashSet<_> = snapshot.active_restrictions.iter().collect();
    if expected.len() != ledger.active_restrictions.len()
        || applied.len() != snapshot.active_restrictions.len()
        || expected != applied
        || snapshot
            .active_restrictions
            .iter()
            .any(|reference| reference.action != "suppress")
    {
        return Err("restored restrictions do not match current ledger".into());
    }
    Ok(())
}

fn verify_release_manifest(path: &Path, expected_digest: &str) -> Result<(), String> {
    let bytes = fs::read(path).map_err(|_| "release manifest is unavailable".to_string())?;
    let manifest: Value =
        serde_json::from_slice(&bytes).map_err(|_| "release manifest is invalid".to_string())?;
    let actual = format!("{:x}", Sha256::digest(canonical_json(&manifest).as_bytes()));
    if expected_digest != actual {
        return Err("release manifest digest does not match trusted reference".into());
    }
    for field in [
        "manifest_version",
        "release_id",
        "profile",
        "ruleset_version",
    ] {
        if manifest
            .get(field)
            .and_then(Value::as_str)
            .is_none_or(str::is_empty)
        {
            return Err(format!("release manifest field is missing: {field}"));
        }
    }
    Ok(())
}

pub fn parse_proxy_config(
    mode: &str,
    trust_proxy: Option<&str>,
    trusted_cidrs: Option<&str>,
) -> Result<ProxyConfig, &'static str> {
    let trust_forwarded_for = match trust_proxy {
        None if mode == "development" => false,
        None => return Err("UEC_TRUST_PROXY must be explicitly set in production"),
        Some("true") => true,
        Some("false") => false,
        Some(_) => return Err("UEC_TRUST_PROXY must be true or false"),
    };
    let cidr_text = trusted_cidrs.unwrap_or("");
    let cidrs: Result<Vec<_>, _> = cidr_text
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(IpNet::from_str)
        .collect();
    let cidrs = cidrs.map_err(|_| "UEC_TRUSTED_PROXY_CIDRS contains an invalid network")?;
    if trust_forwarded_for && cidrs.is_empty() {
        return Err("UEC_TRUSTED_PROXY_CIDRS is required when proxy trust is enabled");
    }
    if !trust_forwarded_for && !cidrs.is_empty() {
        return Err("UEC_TRUSTED_PROXY_CIDRS requires UEC_TRUST_PROXY=true");
    }
    Ok(ProxyConfig {
        trust_forwarded_for,
        trusted_proxy_cidrs: cidrs,
    })
}

pub fn peer_is_trusted_proxy(peer: IpAddr, config: &ProxyConfig) -> bool {
    config
        .trusted_proxy_cidrs
        .iter()
        .any(|network| network.contains(&peer))
}

pub fn validate_startup(
    mode: &str,
    ledger_path: Option<&str>,
    snapshot_path: Option<&str>,
    manifest_path: Option<&str>,
    manifest_digest: Option<&str>,
) -> Result<StartupGateReport, String> {
    if mode != "production" {
        return Ok(StartupGateReport {
            restriction_ledger: "not_required_development",
            release_manifest: "not_required_development",
        });
    }
    let ledger_path = ledger_path
        .filter(|value| !value.trim().is_empty())
        .ok_or("UEC_RESTRICTION_LEDGER_PATH is required in production")?;
    let snapshot_path = snapshot_path
        .filter(|value| !value.trim().is_empty())
        .ok_or("UEC_RESTORED_RESTRICTION_SNAPSHOT_PATH is required in production")?;
    let manifest_path = manifest_path
        .filter(|value| !value.trim().is_empty())
        .ok_or("UEC_RELEASE_MANIFEST_PATH is required in production")?;
    let manifest_digest = manifest_digest
        .filter(|value| !value.trim().is_empty())
        .ok_or("UEC_RELEASE_MANIFEST_SHA256 is required in production")?;
    if manifest_digest.len() != 64
        || !manifest_digest
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(
            "UEC_RELEASE_MANIFEST_SHA256 must be 64 lowercase hexadecimal characters".into(),
        );
    }
    verify_ledger(Path::new(ledger_path), Path::new(snapshot_path))?;
    verify_release_manifest(Path::new(manifest_path), manifest_digest)?;
    Ok(StartupGateReport {
        restriction_ledger: "verified",
        release_manifest: "verified",
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn production_requires_independent_control_plane_inputs() {
        assert!(validate_startup("production", None, None, None, None).is_err());
        assert!(parse_proxy_config("production", Some("true"), Some("10.0.0.0/8")).is_ok());
        assert!(parse_proxy_config("production", Some("true"), Some("10.0.0.1")).is_err());
    }

    #[test]
    fn startup_accepts_matching_synthetic_ledger_and_manifest() {
        let dir = std::env::temp_dir().join(format!(
            "uec-private-gate-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&dir).unwrap();
        let ledger = json!({"schema_version":1,"revision":"synthetic-r1","active_restrictions":[{"source_id":"synthetic","source_record_key":"opaque-1","scope":"whole_record","action":"suppress"}]});
        let ledger_digest = format!("{:x}", Sha256::digest(canonical_json(&ledger).as_bytes()));
        let ledger = json!({"schema_version":1,"revision":"synthetic-r1","ledger_sha256":ledger_digest,"active_restrictions":ledger["active_restrictions"].clone()});
        let snapshot = json!({"ledger_revision":"synthetic-r1","ledger_sha256":ledger["ledger_sha256"].clone(),"active_restrictions":ledger["active_restrictions"].clone()});
        let manifest = json!({"manifest_version":"v1","release_id":"synthetic","profile":"official","ruleset_version":"synthetic-v1"});
        let manifest_digest = format!("{:x}", Sha256::digest(canonical_json(&manifest).as_bytes()));
        let ledger_path = dir.join("ledger.json");
        let snapshot_path = dir.join("snapshot.json");
        let manifest_path = dir.join("manifest.json");
        fs::write(&ledger_path, serde_json::to_vec(&ledger).unwrap()).unwrap();
        fs::write(&snapshot_path, serde_json::to_vec(&snapshot).unwrap()).unwrap();
        fs::write(&manifest_path, canonical_json(&manifest)).unwrap();
        assert_eq!(
            validate_startup(
                "production",
                ledger_path.to_str(),
                snapshot_path.to_str(),
                manifest_path.to_str(),
                Some(&manifest_digest)
            )
            .unwrap()
            .restriction_ledger,
            "verified"
        );
        fs::remove_dir_all(&dir).unwrap();
    }
}
