import json
import base64
import hashlib
import hmac

def encrypt_payload(payload):
    """
    Encrypts the ApplicationData.Payload field if ApplicationData.Encrypt is true.
    Uses HMAC-SHA256 encryption with the key "sudhir1234567890" - no external dependencies needed!
    """
    # Check if encryption is required
    encrypt_flag = payload.get('ApplicationData.Encrypt', 'false').lower()
    
    if encrypt_flag == 'true':
        # Get the payload to encrypt
        data_to_encrypt = payload.get('ApplicationData.Payload', '')
        
        if data_to_encrypt:
            # Use a secret key (in production, use AWS Secrets Manager or env variable)
            secret_key = b'sudhir1234567890'
            
            # Create HMAC-SHA256 hash (secure and built-in to Python)
            data_bytes = data_to_encrypt.encode('utf-8')
            hmac_hash = hmac.new(secret_key, data_bytes, hashlib.sha256).digest()
            
            # Combine original data with hash for integrity verification
            # Format: base64(data) + ":" + base64(hmac)
            data_b64 = base64.b64encode(data_bytes).decode('utf-8')
            hmac_b64 = base64.b64encode(hmac_hash).decode('utf-8')
            encrypted_value = f"{data_b64}:{hmac_b64}"
            
            # Update the payload with encrypted value
            payload['ApplicationData.Payload'] = encrypted_value
            
            # Mark as encrypted
            payload['ApplicationData.Encrypted'] = 'true'
    
    return payload

def lambda_handler(event, context):
    """
    Firehose transformation Lambda handler.
    Receives records from Kinesis Firehose, transforms/enriches them, and returns the result.
    
    Expected event structure from Firehose:
    {
        "invocationId": "...",
        "deliveryStreamArn": "...",
        "region": "us-east-1",
        "records": [
            {
                "recordId": "...",
                "approximateArrivalTimestamp": ...,
                "data": "base64-encoded-data"
            }
        ]
    }
    
    Must return:
    {
        "records": [
            {
                "recordId": "...",
                "result": "Ok" | "Dropped" | "ProcessingFailed",
                "data": "base64-encoded-transformed-data"
            }
        ]
    }
    """
    print(f"Received {len(event['records'])} records for transformation")
    
    output_records = []
    
    for record in event['records']:
        record_id = record['recordId']
        
        try:
            # Decode the base64-encoded data from Firehose
            payload_bytes = base64.b64decode(record['data'])
            payload_str = payload_bytes.decode('utf-8')
            
            print(f"Processing record {record_id}: {payload_str}")
            
            # Parse JSON payload
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                # If not JSON, treat as raw text
                payload = {'message': payload_str}
            
            # Apply encryption if required (same logic as before)
            payload = encrypt_payload(payload)
            
            print(f"Transformed record {record_id}: {json.dumps(payload)}")
            
            # Convert back to JSON string with newline
            output_data = json.dumps(payload) + '\n'
            
            # Base64 encode for Firehose
            output_data_b64 = base64.b64encode(output_data.encode('utf-8')).decode('utf-8')
            
            # Add to output records with success status
            output_records.append({
                'recordId': record_id,
                'result': 'Ok',
                'data': output_data_b64
            })
            
        except Exception as e:
            print(f"Error processing record {record_id}: {str(e)}")
            
            # Return the original record with failure status
            output_records.append({
                'recordId': record_id,
                'result': 'ProcessingFailed',
                'data': record['data']  # Return original data on failure
            })
    
    print(f"Successfully processed {len(output_records)} records")
    
    # Return transformed records to Firehose
    return {
        'records': output_records
    }
