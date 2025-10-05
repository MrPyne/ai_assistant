"""Utilities to recursively decode base64-encoded strings inside JSON-like structures.

Function:
- decode_base64_in_structure(obj): Recursively traverses dicts, lists, tuples and decodes any string
  value (including dict keys) that is valid base64 and decodes to UTF-8. Non-base64 strings are left
  unchanged. Non-string types are returned unmodified. The original input is not modified (a new
  structure is returned).

Behavior notes:
- Only strings that are valid base64 (base64 alphabet and proper padding) and whose decoded bytes
  can be decoded as UTF-8 will be replaced by their decoded UTF-8 string.
- Empty strings are not decoded.
- Dict keys that are strings will also be decoded. If decoding produces duplicate keys, later
  keys will overwrite earlier ones (same behavior as normal dict assignment).
"""

from typing import Any
import base64
import binascii


def _try_decode_base64_string(s: str) -> str:
    """Return the decoded UTF-8 string if s is valid base64 and decodes to UTF-8.
    Otherwise return the original string.
    """
    if not isinstance(s, str):
        return s
    stripped = s.strip()
    if stripped == "":
        return s
    # Reject obvious non-base64 characters quickly
    try:
        decoded_bytes = base64.b64decode(stripped, validate=True)
    except (binascii.Error, ValueError):
        return s
    # If decoded bytes are valid UTF-8, return decoded string; otherwise leave original
    try:
        decoded_str = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return s
    # Additional sanity: ensure encoding the decoded bytes yields the same base64 (allowing
    # differences in padding normalization). Compare without padding and ignoring newline.
    normalized_input = stripped.rstrip("=")
    normalized_reencoded = base64.b64encode(decoded_bytes).decode("ascii").rstrip("=")
    if normalized_input == normalized_reencoded:
        return decoded_str
    # If re-encoding doesn't match (rare), don't decode to avoid false positives.
    return s


def decode_base64_in_structure(obj: Any) -> Any:
    """Recursively traverse obj and decode any strings that are valid base64-encoded UTF-8.

    Supported container types: dict, list, tuple. Other types are returned unchanged.
    Dict keys that are strings will also be processed and replaced if decodable.
    """
    if isinstance(obj, str):
        return _try_decode_base64_string(obj)
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            new_key = _try_decode_base64_string(k) if isinstance(k, str) else k
            new_value = decode_base64_in_structure(v)
            new_dict[new_key] = new_value
        return new_dict
    if isinstance(obj, list):
        return [decode_base64_in_structure(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(decode_base64_in_structure(item) for item in obj)
    # Other JSON-like primitive types (int, float, bool, None) left untouched
    return obj


# Small example when run as script
if __name__ == "__main__":
    example = {
        "aGVsbG8=": "V29ybGQ=",
        "nested": ["SGVsbG8gd29ybGQ=", "not base64", 123],
    }
    print(decode_base64_in_structure(example))
