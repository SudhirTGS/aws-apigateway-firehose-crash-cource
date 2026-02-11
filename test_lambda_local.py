"""
Local test script for Lambda function
Run this to test the lambda_firehose_handler.py locally without SAM
"""
import json
import sys
from unittest.mock import Mock, patch

# Import the Lambda handler
from lambda_firehose_handler import lambda_handler, encrypt_payload

def create_api_gateway_event(payload):
    """
    Creates a mock API Gateway event with the given payload
    """
    return {
        "body": json.dumps(payload),
        "resource": "/",
        "path": "/",
        "httpMethod": "POST",
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "application/json"
        },
        "requestContext": {
            "requestId": "test-request-id",
            "http": {
                "method": "POST",
                "path": "/"
            }
        }
    }

def test_encryption_only():
    """
    Test 1: Test just the encryption function
    """
    print("\n" + "="*60)
    print("TEST 1: Testing Encryption Function Only")
    print("="*60)
    
    test_payload = {
        "ApplicationData.Encrypt": "true",
        "ApplicationData.Payload": "sudhir kilani",
        "ApplicationData.Message": "test message",
        "ApplicationData.MessageCode": "STARTLOG",
        "ApplicationData.TransactionID": "123456",
        "LogHeader.SourceAppName": "mule-apigateway-poc-v1"
    }
    
    print("\nOriginal Payload:")
    print(json.dumps(test_payload, indent=2))
    
    # Test encryption
    encrypted_payload = encrypt_payload(test_payload.copy())
    
    print("\nEncrypted Payload:")
    print(json.dumps(encrypted_payload, indent=2))
    
    # Check if payload was encrypted
    if encrypted_payload["ApplicationData.Payload"] != "sudhir kilani":
        print("\n✅ SUCCESS: Payload was encrypted!")
        print(f"Encrypted value: {encrypted_payload['ApplicationData.Payload']}")
    else:
        print("\n❌ FAILED: Payload was not encrypted!")
    
    return encrypted_payload

def test_lambda_handler_with_mock_firehose():
    """
    Test 2: Test the full Lambda handler with mocked Firehose
    """
    print("\n" + "="*60)
    print("TEST 2: Testing Full Lambda Handler (Mocked Firehose)")
    print("="*60)
    
    test_payload = {
        "ApplicationData.Encrypt": "true",
        "ApplicationData.Payload": "sudhir kilani",
        "ApplicationData.Message": "test message",
        "ApplicationData.MessageCode": "STARTLOG",
        "ApplicationData.TransactionID": "123456",
        "LogHeader.SourceAppName": "mule-apigateway-poc-v1"
    }
    
    # Create API Gateway event
    event = create_api_gateway_event(test_payload)
    context = Mock()
    
    print("\nAPI Gateway Event:")
    print(json.dumps(event, indent=2))
    
    # Mock the Firehose client
    with patch('lambda_firehose_handler.firehose_client') as mock_firehose:
        # Configure mock to return success
        mock_firehose.put_record.return_value = {
            'RecordId': 'test-record-id-12345',
            'Encrypted': False
        }
        
        # Call the Lambda handler
        response = lambda_handler(event, context)
        
        print("\nLambda Response:")
        print(json.dumps(response, indent=2))
        
        # Check if Firehose was called
        if mock_firehose.put_record.called:
            print("\n✅ SUCCESS: Firehose put_record was called!")
            
            # Get the data that was sent to Firehose
            call_args = mock_firehose.put_record.call_args
            firehose_data = call_args[1]['Record']['Data'].decode('utf-8')
            
            print("\nData sent to Firehose:")
            print(firehose_data)
            
            # Parse and display
            try:
                parsed_data = json.loads(firehose_data.strip())
                print("\nParsed Firehose Data:")
                print(json.dumps(parsed_data, indent=2))
                
                # Verify encryption
                if parsed_data.get("ApplicationData.Payload") != "sudhir kilani":
                    print("\n✅ VERIFIED: Payload was encrypted before sending to Firehose!")
                else:
                    print("\n❌ WARNING: Payload was NOT encrypted!")
                    
            except json.JSONDecodeError as e:
                print(f"\n❌ ERROR: Could not parse Firehose data: {e}")
        else:
            print("\n❌ FAILED: Firehose was not called!")
        
        # Check response status
        if response.get('statusCode') == 200:
            print("\n✅ SUCCESS: Lambda returned 200 status code")
        else:
            print(f"\n❌ FAILED: Lambda returned {response.get('statusCode')} status code")
    
    return response

def test_without_encryption():
    """
    Test 3: Test with encryption disabled
    """
    print("\n" + "="*60)
    print("TEST 3: Testing Without Encryption (Encrypt=false)")
    print("="*60)
    
    test_payload = {
        "ApplicationData.Encrypt": "false",  # Disabled
        "ApplicationData.Payload": "sudhir kilani",
        "ApplicationData.Message": "test message",
        "ApplicationData.MessageCode": "STARTLOG",
        "ApplicationData.TransactionID": "123456",
        "LogHeader.SourceAppName": "mule-apigateway-poc-v1"
    }
    
    print("\nOriginal Payload (Encrypt=false):")
    print(json.dumps(test_payload, indent=2))
    
    # Test encryption function
    result = encrypt_payload(test_payload.copy())
    
    print("\nResult:")
    print(json.dumps(result, indent=2))
    
    # Verify payload was NOT encrypted
    if result["ApplicationData.Payload"] == "sudhir kilani":
        print("\n✅ SUCCESS: Payload was NOT encrypted (as expected)")
    else:
        print("\n❌ FAILED: Payload was encrypted when it shouldn't be!")
    
    return result

if __name__ == "__main__":
    print("\n")
    print("*" * 60)
    print("   LAMBDA HANDLER LOCAL TEST SUITE")
    print("*" * 60)
    
    try:
        # Run all tests
        test_encryption_only()
        test_lambda_handler_with_mock_firehose()
        test_without_encryption()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
