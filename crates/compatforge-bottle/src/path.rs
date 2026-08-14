use std::collections::{BTreeMap, BTreeSet};
use std::path::{Component, Path};

use crate::snapshot::{MAX_PATH_BYTES, MAX_PATH_DEPTH};
use unicode_normalization::UnicodeNormalization as _;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct InvalidPath;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum EntryKind<'a> {
    File,
    Directory,
    Link(&'a str),
}

pub(crate) fn validate_relative_path(value: &str) -> Result<(), InvalidPath> {
    let mut depth = 0_usize;
    if value.is_empty() || value.len() > MAX_PATH_BYTES {
        return Err(InvalidPath);
    }
    for component in value.split('/') {
        depth = depth.checked_add(1).ok_or(InvalidPath)?;
        validate_component(component)?;
    }
    if depth > MAX_PATH_DEPTH {
        return Err(InvalidPath);
    }
    Ok(())
}

pub(crate) fn validate_component(value: &str) -> Result<(), InvalidPath> {
    if value.is_empty()
        || matches!(value, "." | "..")
        || value.ends_with([' ', '.'])
        || !value.nfc().eq(value.chars())
        || value
            .chars()
            .any(|character| character.is_control() || "<>:\"\\|?*".contains(character))
        || is_reserved_device_name(value)
    {
        return Err(InvalidPath);
    }
    Ok(())
}

pub(crate) fn validate_graph<'a>(
    entries: impl IntoIterator<Item = (&'a str, EntryKind<'a>)>,
) -> Result<(), InvalidPath> {
    let mut folded = BTreeMap::<String, EntryKind<'a>>::new();
    let mut exact = BTreeMap::<&'a str, EntryKind<'a>>::new();
    for (path, kind) in entries {
        validate_relative_path(path)?;
        if let EntryKind::Link(target) = kind {
            validate_relative_path(target)?;
        }
        let collision_key = collision_key(path);
        if folded.insert(collision_key.clone(), kind).is_some() || exact.insert(path, kind).is_some() {
            return Err(InvalidPath);
        }
        let mut parent = collision_key.as_str();
        while let Some(index) = parent.rfind('/') {
            parent = &parent[..index];
            if folded
                .get(parent)
                .is_some_and(|entry| !matches!(entry, EntryKind::Directory))
            {
                return Err(InvalidPath);
            }
        }
        if !matches!(kind, EntryKind::Directory) {
            let descendant_prefix = format!("{collision_key}/");
            if folded.keys().any(|candidate| candidate.starts_with(&descendant_prefix)) {
                return Err(InvalidPath);
            }
        }
    }

    for path in exact.keys() {
        let mut parent = *path;
        while let Some((candidate, _)) = parent.rsplit_once('/') {
            if !matches!(exact.get(candidate), Some(EntryKind::Directory)) {
                return Err(InvalidPath);
            }
            parent = candidate;
        }
    }

    for (path, kind) in &exact {
        let EntryKind::Link(mut target) = kind else {
            continue;
        };
        let mut visited = BTreeSet::from([*path]);
        loop {
            let target_kind = exact.get(target).ok_or(InvalidPath)?;
            let EntryKind::Link(next) = target_kind else {
                break;
            };
            if !visited.insert(target) {
                return Err(InvalidPath);
            }
            target = next;
        }
    }
    Ok(())
}

pub(crate) fn normalize_link_target(link_path: &str, raw_target: &Path) -> Result<String, InvalidPath> {
    if raw_target.is_absolute() {
        return Err(InvalidPath);
    }
    let mut components = link_path
        .rsplit_once('/')
        .map_or_else(Vec::new, |(parent, _)| parent.split('/').map(str::to_owned).collect());
    for component in raw_target.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                components.pop().ok_or(InvalidPath)?;
            }
            Component::Normal(value) => {
                let value = value.to_str().ok_or(InvalidPath)?;
                validate_component(value)?;
                components.push(value.to_owned());
            }
            Component::Prefix(_) | Component::RootDir => return Err(InvalidPath),
        }
    }
    let target = components.join("/");
    validate_relative_path(&target)?;
    Ok(target)
}

fn collision_key(path: &str) -> String {
    let mut folded = String::with_capacity(path.len());
    for character in path.chars().flat_map(char::to_lowercase) {
        match character {
            '\u{03c2}' => folded.push('\u{03c3}'),
            '\u{00df}' => folded.push_str("ss"),
            _ => folded.push(character),
        }
    }
    folded
}

fn is_reserved_device_name(value: &str) -> bool {
    let stem = value.split('.').next().unwrap_or(value);
    let upper = stem.to_uppercase();
    matches!(upper.as_str(), "CON" | "PRN" | "AUX" | "NUL" | "CONIN$" | "CONOUT$")
        || reserved_numbered_device(&upper, "COM")
        || reserved_numbered_device(&upper, "LPT")
}

fn reserved_numbered_device(value: &str, prefix: &str) -> bool {
    value.strip_prefix(prefix).is_some_and(|suffix| {
        matches!(
            suffix,
            "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "¹" | "²" | "³"
        )
    })
}
