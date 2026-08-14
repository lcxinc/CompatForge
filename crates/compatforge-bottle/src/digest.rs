use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fmt::Write as _;
use std::io::{self, Read, Write};

pub(crate) const STREAM_BUFFER_BYTES: usize = 64 * 1024;

pub(crate) fn sha256_bytes(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format_digest(hasher.finalize())
}

pub(crate) fn copy_and_digest(input: &mut impl Read, output: &mut impl Write) -> io::Result<(String, u64)> {
    let mut hasher = Sha256::new();
    let mut total = 0_u64;
    let mut buffer = [0_u8; STREAM_BUFFER_BYTES];
    loop {
        let read = input.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        output.write_all(&buffer[..read])?;
        hasher.update(&buffer[..read]);
        total = total
            .checked_add(u64::try_from(read).expect("a buffer length fits in u64"))
            .ok_or_else(|| io::Error::other("stream length overflow"))?;
    }
    Ok((format_digest(hasher.finalize()), total))
}

pub(crate) fn digest_reader(input: &mut impl Read) -> io::Result<(String, u64)> {
    let mut sink = io::sink();
    copy_and_digest(input, &mut sink)
}

pub(crate) fn canonical_compact_json(value: &impl Serialize) -> serde_json::Result<Vec<u8>> {
    canonical_json(value, false)
}

pub(crate) fn canonical_pretty_json_lf(value: &impl Serialize) -> serde_json::Result<Vec<u8>> {
    let mut bytes = canonical_json(value, true)?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn canonical_json(value: &impl Serialize, pretty: bool) -> serde_json::Result<Vec<u8>> {
    let value = serde_json::to_value(value)?;
    let mut bytes = Vec::new();
    render_canonical_value(&value, pretty, 0, &mut bytes)?;
    Ok(bytes)
}

fn render_canonical_value(value: &Value, pretty: bool, depth: usize, output: &mut Vec<u8>) -> serde_json::Result<()> {
    match value {
        Value::Array(items) => {
            output.push(b'[');
            if !items.is_empty() {
                if pretty {
                    output.push(b'\n');
                }
                for (index, item) in items.iter().enumerate() {
                    if index > 0 {
                        output.push(b',');
                        if pretty {
                            output.push(b'\n');
                        }
                    }
                    if pretty {
                        append_indent(output, depth + 1);
                    }
                    render_canonical_value(item, pretty, depth + 1, output)?;
                }
                if pretty {
                    output.push(b'\n');
                    append_indent(output, depth);
                }
            }
            output.push(b']');
        }
        Value::Object(object) => {
            output.push(b'{');
            if !object.is_empty() {
                if pretty {
                    output.push(b'\n');
                }
                let mut members = object.iter().collect::<Vec<_>>();
                members.sort_unstable_by(|(left, _), (right, _)| left.cmp(right));
                for (index, (key, member)) in members.into_iter().enumerate() {
                    if index > 0 {
                        output.push(b',');
                        if pretty {
                            output.push(b'\n');
                        }
                    }
                    if pretty {
                        append_indent(output, depth + 1);
                    }
                    output.extend(serde_json::to_vec(key)?);
                    output.push(b':');
                    if pretty {
                        output.push(b' ');
                    }
                    render_canonical_value(member, pretty, depth + 1, output)?;
                }
                if pretty {
                    output.push(b'\n');
                    append_indent(output, depth);
                }
            }
            output.push(b'}');
        }
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {
            output.extend(serde_json::to_vec(value)?);
        }
    }
    Ok(())
}

fn append_indent(output: &mut Vec<u8>, depth: usize) {
    for _ in 0..depth {
        output.extend_from_slice(b"  ");
    }
}

fn format_digest(bytes: impl AsRef<[u8]>) -> String {
    let mut value = String::with_capacity(71);
    value.push_str("sha256:");
    for byte in bytes.as_ref() {
        write!(&mut value, "{byte:02x}").expect("writing to a string cannot fail");
    }
    value
}
