import sys
import os

# Add backend to path
sys.path.append(os.path.abspath("backend"))

from app.core.security import encrypt_data, decrypt_data

test_val = "sk-1234567890"
encrypted = encrypt_data(test_val)
decrypted = decrypt_data(encrypted)

print(f"Original: {test_val}")
print(f"Encrypted: {encrypted}")
print(f"Decrypted: {decrypted}")

if test_val == decrypted:
    print("SUCCESS: Encryption/Decryption works!")
else:
    print("FAILURE: Values don't match!")
