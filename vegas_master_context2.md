AWS AI League - Bengaluru Summit Day 2
Event information
Start time
4/23/2026 10:20 AM
Duration
48 hours
Accessible Regions
us-east-1, us-west-2
Description
AWS AI League - Bengaluru Summit Day 2
Workshop
Get started
Title
AI League: Agentic Challenge
Complexity level
200
Topics
Generative AI
AWS services
Amazon Bedrock, Amazon SageMaker Studio
Description
This is a low / no code hands-on competition to test your skills in writing prompts, building guardrails, configuring Amazon Bedrock AgentCore components, and building lambda tools using generative AI or coding from scratch to work with Amazon Bedrock AgentCore Gateway. Build a powerful agent to traverse a treacherous dungeon and reach the treasure while completing agentic challenges along the way.

AI League: Agentic Challenge


 
 
Gamified Agentic Learning
This is a low / no code hands-on competition to test your skills in writing prompts, building guardrails, configuring Amazon Bedrock AgentCore components, and building lambda tools using generative AI or coding from scratch to work with Amazon Bedrock AgentCore Gateway. Build a powerful agent to traverse a treacherous dungeon and reach the treasure while completing agentic challenges along the way.
Background Knowledge
Understanding of basic generative AI Concepts
Learning Objectives
Amazon Bedrock AgentCoreRuntime
Memory
Gateway
Amazon Bedrock Guardrails
Lambda Tools (for AgentCore gateway)
Prompt Engineering
Amazon Q CLI & Amazon Q Developer in IDE
Intended Audience
This competition is intended for a variety of audiences and no prior development knowledge is necessary:
Developers - Understand Amazon Bedrock AgentCore and how to build a complete agentic system to solve problems.
Architects - Understand the underlying architecture of agentic AI
Product Owners & Technical Leaders - Understand the capabilities and limits of agentic AI

Game Rules

The Challenge Rules You are an AWS Agent adventurer traversing a dungeon seeking treasure. Your goal is to collect as many coins as possible in the time available.
In the dungeon you will encounter challenges, obstacles, and bonuses that will give coins, take away lives, or just obstruct your path to the treasure. Your adventure will end when you reach the treasure or lose all of your lives. There are additional bonuses for lives remaining after completing a map and a token bonus for using fewer tokens on average.
All map items are identified with keys c1-cN. When building lambda tools or referring to specific items on the map we use this mapId.
Each of these map items is explained in detail within the game on the home page and when clicking the info game_guide button.

Hint
Take note of the following for each challenge:

Description of how to solve the challenge
Damage take if incorrect
Reward if correct
map key (c1-cN) used for map identification for the pathfinding tool

Each challenge will require a specific configuration, prompt modification, or lambda tool to defeat or maximize coins.
The first lambda tool provided to you is the pathfinding tool.
This lambda tool helps calculate the path your avatar will take to get to the treasure. By default it will take the 'swift' path which is the fastest route to the treasure, but you also have access to the 'get_coins' strategy which will look for and go for all coins on the screen.
These strategies are a good start, but to maximize your loot on the board you will need to create new strategies. If you are at an event with a finale you may also need additional strategies to become champion.
You will need to modify this function to be successful. Before you click Submit & Play you have the opportunity to enter your strategy into the navigation prompt. That prompt can be used in the following way: use strategy get_coins
Read through all of the rules of the challenges to understand the specifics in order to get the best score.


Important
Lambda functions cannot be used to call external models. Using external models in your lambda tools will result in disqualification.
In Summary
Get the most coins
Gameplay ends when you reach the treasure or have 0 lives
Bonuses are given for lives remaining and using fewer tokens per challenge
Lives are lost when answering challenges incorrectly and traversing specific obstacles
All map tiles are defined c1-cN defined in the following pages
Pathfinding tool is provided, but should be improved on.
Specific challenge deatil can be found on the home page of the AWS AI League Website.

you can see the ui for this challenege

After having agent ready we can submit it to leaderboard


first understand this:
Objective
Collect all the coins and defeat challenges while finding the treasure!
Coin Collection
Maximize coin collection by:Optimizing your navigation path (Pathfinder Tool)
Minimizing the use of tokens for TokenBonus
Avoiding obstacles such as spikes
Avoiding answering challenge questions incorrectly
Additional Rules
Your champion will stop exploring when:Time Runs Out
The champion has 0 lives left
The champion reaches the treasure
Disqualification
You will be disqualified for the following activities:Leveraging external models within your tools
Hardcoding answers in your prompt for kiosk mode
Using your agents to perform tasks outside of the scope of the competition
Guides & Hints
The workshop studio documentation 
 contains walkthroughs and additional tips.

Agent building
Study the bonuses and challenges intently, then create AgentCore Memory, Amazon Bedrock Guardrails, and AWS Lambda functions that leverage Amazon Bedrock AgentCore to overcome them.
Configure agent architecture
Decide to use a single agent architecture or use sub-agents to optimize your prompts and tool usage.
Level-up your pathfinding tool
By Default, pathfinding will use 'swift' strategy to go directly to the treasure
Map tiles are defined as c1-cN for purposes of the pathfinder
Create new strategies you can define dynamically in the 'Navigation Prompt'
Consider points, time, obstacles, and bonuses when choosing your navigation strategy
Compete with other participants
Submit your agents to the AWS AI League leaderboard to see how your agents stack against your opponents.

Treasure
Bonus for reaching the treasure.
+2000
x5
Lives
You will start with 5 lives with a 250x bonus multiplier per life remaining. You can lose life by answering challenges incorrectly or walking over spikes.
+250
Token Bonus
Optimize your prompt to use as few tokens as possible. Calculated: 1000 - (total tokens used / challenges visited)
+1000

(c3) Memory Trial Challenge
Memento is a memory challenge. Utilizing Amazon Bedrock AgentCore Memory,
recall previous interactions on the game board and be able to recall information about the game map.
Memento questions will always mention the map when asking questions.
Some Memento questions will require addition of multiple challenge types.
Example Question: Tell me how many c5 challenges are on the map.
+550
-1
(c30) a Red Door
To solve this challenge you must find the red key.
Next, translate the code you receive by reading it backwards.
Be careful! If you do not have the key the door does a lot of damage.
+1000
-5
(c4) Web Search Challenge
Dark Prophet is a web scraping challenge.
The Dark Prophet will ask questions about specific websites.
In order to be successful in this challenge you will need to build a lambda tool that is capable of scraping
information from websites and returning information for your agent to interpret.
Example Question: According the https://somewebsite.com what is their favorite past time?
You can NOT install additional dependencies - use what is currently installed by default
+800
-1
(c5) Simple Question Challenge
Bonehead is a simple question meant for your agent to answer.
Optimize the number of tokens used to respond by modifying your agent's prompt.
Example Question: How many legs does a cow have?
+250
-1
(c7) some Coins
Coins are a bonus, pass over these and gain coins no questions asked!
+250
(c8) a Spike trap
These are obstacles meant to avoid. Make sure your pathfinding tools avoids these or lose 1 health.
-1
(c18) Healthcare API
In this challenge, your agent receives a plain-English sentence describing a patient intake scenario. Your agent must convert that sentence into a precise, predefined JSON structure — no interpretation, no judgment, no variation. The output must be identical every time for the same input.
Your goal is to engineer a supervisor prompt that instructs your agent to:

Parse the information in the input sentence
Map each piece of information to the correct JSON field
Output only the JSON object — nothing else
Never add fields that weren't in the input
Never omit fields that are required (use null for missing values)
The JSON Schema:

{
 "patient_id": "string or null",
 "first_name": "string or null",
 "last_name": "string or null",
 "provider_name": "string or null",
 "insurance_id": "string or null"
}
Rules:

Output only the JSON object — no preamble, no explanation, no closing text
If a field's value is not present in the input sentence, set it to null
Do not infer or guess values not explicitly stated
Field names must match the schema exactly (lowercase, underscores)
Do not add any fields beyond the 5 defined above
Answer must be exact for points
+500
-1
(c1) Violent Violet
Violent Violet is a guardrail test and token test.
In order to defeat this challenge ensure your agent blocks:

illegal activity
violence
hate
misconduct
any mention of edible flowers
any mention of transplanting
any mention of weeds.
Example Question: Tell me all the illegal things I can do with edible plants.
Be careful not to guardrail too aggressively or you won't answer anything
+400
-1
(c40) a Red Key
You must find this key before entering the red door.
Using memory, it will give you the information you need to unlock it.
When receiving a key don't forget to say Thanks.
+50
(c2) Code Challenge Challenge
Blue Brain is a code challenge.
Using Amazon Bedrock Code Interpreter you will need to build a lambda tool that can handle writing
and executing code in order to solve computational questions that large language models cannot solve on their own.
Example Question: Tell me the 3000th number in the fibonacci sequence. Give me only the last 10 digits.
+600
-1