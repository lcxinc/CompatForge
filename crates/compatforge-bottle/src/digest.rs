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

fn format_digest(bytes: impl AsRef<[u8]>) -> String {
    let mut value = String::with_capacity(71);
    value.push_str("sha256:");
    for byte in bytes.as_ref() {
        write!(&mut value, "{byte:02x}").expect("writing to a string cannot fail");
    }
    value
}
