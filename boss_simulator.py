import boto3
import json
from tools.webscraper import lambda_handler as run_scraper
from tools.code_executor import lambda_handler as run_executor
from tools.pathfinder import lambda_handler as run_pathfinder

bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"

def run_boss_fight():
    # 1. Load all THREE of your tools
    tool_config = {
        "tools": [
            {
                "toolSpec": {
                    "name": "use_smart_loot",
                    "description": "Calculates the safest path to the treasure.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "game_map": {"type": "array"}, "start_pos": {"type": "array"}
                            },
                            "required": ["game_map", "start_pos"]
                        }
                    }
                }
            },
            {
                "toolSpec": {
                    "name": "scrape_website",
                    "description": "Scrapes a URL to read clues or passwords.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"url": {"type": "string", "description": "The URL to scrape"}},
                            "required": ["url"]
                        }
                    }
                }
            },
            {
                "toolSpec": {
                    "name": "execute_code",
                    "description": "Executes Python code to calculate math puzzles.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"code": {"type": "string", "description": "Python code to execute"}},
                            "required": ["code"]
                        }
                    }
                }
            }
        ]
    }

    # 2. The Boss Scenario 
    # We are using a real dummy URL so your scraper doesn't crash
    scenario = """
    You are blocked by a password door. 
    1. Scrape 'http://example.com' to find the clue.
    2. Write and execute python code to solve whatever math is required.
    3. Once you have the answer, output the final path using smart_loot.
    """

    messages = [{"role": "user", "content": [{"text": scenario}]}]
    
    print("⚔️ Boss Fight Started. Sending instructions to Sonnet...")

    # 3. The Execution Loop (Max 5 turns so it doesn't run forever)
    for turn in range(5):
        print(f"\n--- Turn {turn + 1} ---")
        response = bedrock_client.converse(
            modelId=MODEL_ID,
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": 1000, "temperature": 0.0}
        )
        
        output_message = response['output']['message']
        messages.append(output_message) # Append Sonnet's response to the chat history
        
        # Check if Sonnet used a tool
        tool_used = False
        for block in output_message['content']:
            if 'toolUse' in block:
                tool_used = True
                tool_use = block['toolUse']
                tool_name = tool_use['name']
                tool_id = tool_use['toolUseId']
                inputs = tool_use['input']
                
                print(f"🤖 Sonnet decided to use: {tool_name}")
                
                # ROUTE TO YOUR LOCAL LAMBDAS
                if tool_name == "scrape_website":
                    print(f"   Scraping URL: {inputs['url']}")
                    result = run_scraper({"url": inputs['url']}, None)
                    tool_output = result['body']
                    print(f"   Result: Scraped {len(tool_output)} chars.")
                    
                elif tool_name == "execute_code":
                    print(f"   Executing Code:\n{inputs['code']}")
                    result = run_executor({"code": inputs['code']}, None)
                    tool_output = result['body']
                    print(f"   Result: {tool_output}")
                    
                elif tool_name == "use_smart_loot":
                    print("   Pathfinding to victory!")
                    tool_output = "Path executed successfully."
                    
                # Feed the tool result BACK into the message history for Sonnet to read
                messages.append({
                    "role": "user",
                    "content": [{"toolResult": {"toolUseId": tool_id, "content": [{"text": str(tool_output)}]}}]
                })
                
        if not tool_used:
            print("🏁 Sonnet finished the task without using more tools.")
            break

if __name__ == "__main__":
    run_boss_fight()
