import re
from typing import List
from eth_utils import keccak

def para_hash(text: str) -> bytes:
    """Hash a paragraph of text deterministically."""
    if not text or not text.strip():
        return keccak(b"")
    # Normalize: lowercase, replace multiple whitespaces with single space, strip
    normalized = re.sub(r'\s+', ' ', text).strip().lower()
    return keccak(normalized.encode('utf-8'))

def merkle_root(hashes: List[bytes]) -> bytes:
    """Compute Merkle root from a list of hashes."""
    if not hashes:
        return b'\x00' * 32
    if len(hashes) == 1:
        return hashes[0]
    
    next_level = []
    for i in range(0, len(hashes), 2):
        if i + 1 < len(hashes):
            next_level.append(keccak(hashes[i] + hashes[i+1]))
        else:
            # If odd number of hashes, duplicate the last one
            next_level.append(keccak(hashes[i] + hashes[i]))
            
    return merkle_root(next_level)
