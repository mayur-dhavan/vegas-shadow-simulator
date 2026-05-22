import boto3
import json

# Initialize the Bedrock client
print("Initializing Bedrock connection...")
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"

def test_sonnet_tool_call():
    # 1. Define the tool exactly how your Lambda works
    tool_config = {
        "tools": [
            {
                "toolSpec": {
                    "name": "use_smart_loot",
                    "description": "Calculates the safest path to the treasure, avoiding c8 spikes and prioritizing c40 keys.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "game_map": {"type": "array", "description": "The 2D game grid array"},
                                "start_pos": {"type": "array", "description": "Current [x,y] coordinates"}
                            },
                            "required": ["game_map", "start_pos"]
                        }
                    }
                }
            }
        ]
    }

    # 2. Create a fake map state (3x3 grid)
    dummy_state = {
        "game_map": [
            ["normal", "normal", "c8"],
            ["normal", "c40", "wall"],
            ["normal", "treasure", "normal"]
        ],
        "start_pos": [0, 0]
    }

    # 3. The 45-Second Drill Prompt
    system_prompt = "You are an autonomous AI agent in a dungeon. Your ONLY goal is to reach the 'treasure'. You MUST use the use_smart_loot tool to move. Do not output conversational text."

    messages = [
        {
            "role": "user",
            "content": [{"text": f"Current State: {json.dumps(dummy_state)}\n\nWhat is your next move?"}]
        }
    ]

    print("Sending map to Claude 3.5 Sonnet on AWS...")
    try:
        response = bedrock_client.converse(
            modelId=MODEL_ID,
            messages=messages,
            system=[{"text": system_prompt}],
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": 500, "temperature": 0.0}
        )
        
        # 4. Parse the response
        response_message = response['output']['message']
        print("\n=== SONNET RESPONSE ===")
        
        for content_block in response_message['content']:
            if 'toolUse' in content_block:
                tool_name = content_block['toolUse']['name']
                tool_input = content_block['toolUse']['input']
                print(f"✅ SUCCESS! Sonnet chose tool: {tool_name}")
                print(f"📦 Payload sent to tool:\n{json.dumps(tool_input, indent=2)}")
                return
            elif 'text' in content_block:
                print(f"⚠️ Warning: Sonnet talked instead of using a tool: {content_block['text']}")
                
    except Exception as e:
        print(f"❌ Error pinging Bedrock: {e}")

if __name__ == "__main__":
    test_sonnet_tool_call()