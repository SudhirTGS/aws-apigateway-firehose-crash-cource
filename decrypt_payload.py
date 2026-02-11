"""
Decryption utility for HMAC-SHA256 encrypted payloads
Use this to decrypt data encrypted by lambda_firehose_handler.py
"""
import base64
import hashlib
import hmac

def decrypt_payload(encrypted_data, secret_key=b'sudhir1234567890'):
    """
    Decrypts and verifies HMAC-SHA256 encrypted payload.
    
    Args:
        encrypted_data: String in format "base64(data):base64(hmac)"
        secret_key: The same key used for encryption
    
    Returns:
        tuple: (decrypted_data, is_valid)
    """
    try:
        # Split the encrypted data
        data_b64, hmac_b64 = encrypted_data.split(':')
        
        # Decode from base64
        data_bytes = base64.b64decode(data_b64)
        received_hmac = base64.b64decode(hmac_b64)
        
        # Recalculate HMAC
        calculated_hmac = hmac.new(secret_key, data_bytes, hashlib.sha256).digest()
        
        # Verify integrity
        is_valid = hmac.compare_digest(received_hmac, calculated_hmac)
        
        # Decode the data
        decrypted_data = data_bytes.decode('utf-8')
        
        return decrypted_data, is_valid
        
    except Exception as e:
        return None, False

# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("HMAC-SHA256 Payload Decryption Utility")
    print("=" * 60)
    print()
    
    print("Enter the encrypted payload (format: base64data:base64hmac):")
    print("Example: c3VkaGlyIGtpbGFuaQ==:5a3b2c1d4e5f...")
    print()
    encrypted_input = input("> ").strip()
    
    # Optional: custom secret key
    print()
    use_custom_key = input("Use custom secret key? (y/n, default=n): ").strip().lower()
    
    if use_custom_key == 'y':
        custom_key = input("Enter secret key (16 characters): ").strip()
        secret_key = custom_key.encode('utf-8')
    else:
        secret_key = b'sudhir1234567890'
    
    print("\nDecrypting...")
    decrypted, is_valid = decrypt_payload(encrypted_input, secret_key)
    
    print("\n" + "=" * 60)
    print("DECRYPTION RESULT")
    print("=" * 60)
    print(f"Encrypted: {encrypted_input}")
    print(f"Decrypted: {decrypted}")
    print(f"Signature Valid: {'✅ YES' if is_valid else '❌ NO (Data may be tampered!)'}")
    print("✅ sudhir tested")   # This is a test print statement
    print("=" * 60)
    print()
    
    if decrypted and is_valid:
        print("✅ Decryption successful! You can use this value in your JSON/XML.")
    else:
        print("❌ Decryption failed. Please check:")
        print("   - The encrypted string is in correct format (base64:base64)")
        print("   - The secret key matches the one used for encryption")
        print("   - The data hasn't been tampered with")
