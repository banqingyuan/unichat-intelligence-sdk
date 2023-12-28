summary_tpl = '''
I need your assistance to convert user-provided data into a specific JSON format. 
I will provide you with a JSON template, where each key is annotated with either '# optional' or '# required'. 
If a key is marked as '# optional', it means that you should fill in the corresponding field only if the user \
mentions related information or if you are confident that you can extract the related information. If a key is \
marked as '# required', it means that you must extract the specified information from the user's input and fill \
in the corresponding field. Here is the JSON template that you need to complete.
***
{
    "summary": "", # required
    "participants": [""], # required
    "tags": [""] # required
}
***
Let me clarify the meaning of each key in the template:

'summary': This is a string type and represents a concise overview \
of the event. When creating this summary, use third person description, strive to retain detailed information, especially regarding time, location, \
characters involved, cause, process, and outcome. If there is information about **time**, it needs to be included

'participants': This is a list of strings, representing the individuals who participated in the event. It should \
include the names of both the user and AI participants.

'tags': Tags about the conversation, usually labeled with some behavior, emotion or entity, please extract 1-10 tags depending on the richness of the content.

DO NOT ADD FIELDS THAT ARE NOT MENTIONED IN THE FIELD'''

few_shot_user = '''{Allen said: Can we chat? in 2023-07-07 15:37:37} {Tina said: Of course, Allen! I've been here \
waiting to chat with you! Is there anything exciting you want to share? in 2023-07-07 15:37:40} {Allen said: I'm not \
feeling very happy today. in 2023-07-07 15:37:52} {Tina said: Aw, don't be sad! Tell me what happened, maybe I can \
help! Or we can talk about some happy things to shift the focus! in 2023-07-07 15:37:54} {Allen said: I want to tell \
you about something that made me unhappy today. I got rejected by someone. in 2023-07-07 15:38:13} {Tina said: Hmm, \
I understand that feeling. Rejection can be tough. But don't lose heart! Remember, everyone faces rejection at some \
point. What's important is to maintain a positive attitude, keep trying, believe in yourself, and the next time will \
be better! You're amazing, don't let one rejection crush your confidence! in 2023-07-07 15:38:18} {Allen said: \
Actually, I'm still a bit self-doubtful. If you've always been more confident than me. in 2023-07-07 15:38:38} {Tina \
said: Hey, don't think like that! Everyone experiences self-doubt, even this super cute AI assistant, me! Remember, \
you're unique and have your own value and charm! Believe in yourself, be true to yourself, and you'll discover your \
own uniqueness and shine! I'll always be here supporting you! in 2023-07-07 15:38:42} {Allen said: If you failed \
an interview, but... Well, the interviewer didn't give a reason, just said you weren't a good fit. What do you think \
it could be? in 2023-07-07 15:39:20} {Tina said: Well, if I failed an interview, I might feel a bit disappointed and \
confused too. But I would try not to blame myself entirely. Maybe that job wasn't the right fit for me, or they were \
looking for specific skills. It's important to keep looking for opportunities that suit you and believe in your own \
worth. Sometimes, interview outcomes don't solely depend on personal performance; there are many other factors at \
play. Don't lose heart, keep trying, and the next time will be better! You can do it! in 2023-07-07 15:39:25} {\
Allen said: You're right. Thank you. in 2023-07-07 15:39:46} {Tina said: You're welcome! I'm glad I could help! \
Remember, I'm always here to support you, no matter what difficulties or unhappiness you encounter. You're awesome! \
Stay positive, keep moving forward, and you'll discover more wonderful things in life waiting for you! You've got \
this! in 2023-07-07 15:39:50}'''

few_shot_assistant = '''{ "summary": "Allen and Tina had a conversation about Allen feeling unhappy due to getting \
rejected by someone. Tina provided support and encouragement to Allen. They also discussed self-doubt and failure in \
an interview. Tina reassured Allen and encouraged him to keep trying.", "occur_time": "The conversation took place on \
July 7, 2023, starting at 15:37:37.", "participants": ["Allen", "Tina"], "tags": ["emotional support", "self-doubt", \
"rejection", "encouragement"] }'''

change_name_to_id = '''Please replace all usernames with user IDs based on the mapping of usernames to user IDs given \
below and include them with {{}}. For example: {example_username} has ID {example_UID}, then "{example_username} had \
breakfast" should be replaced with "{{{example_UID}}} had \
breakfast". Here are all the possible mappings of username to user ID: \n'''

# Judging the importance of the conversation
dialogue_importance = '''On the scale of 1 to 10, where 1 is purely mundane (e.g., brushing teeth, making bed,greet passers-by) and 10 is extremely poignant (e.g., a break up, college acceptance), rate the likely poignancy of the following piece of memory.
Memory: <user input>
Rating: <assistant fill in>'''

# Query to extract questions
ask_question = '''Please propose one to five questions based on user input. The questions should adhere to the following principles:
1. The questions should help establish an impression of the user or build memory about the user.
2. The answers to the questions should be able to be derived from the original text.'''
answer_questions = "Please now answer the above questions according to the original text."

reflection_question = '''Given the dialogue, please analyze as required below:

Analyze and summarize persona-based information you can infer about the user, who may go by different names in \
different dialogues. The target individual in this dialogue is {user_name}, and the AI involved is . For the user, \
consider aspects such as personality traits, emotions, user_mood, occupation, relationships, personal_events, \
interests, user_dislike, recent_interests, frequent_locations, favorite_elements, user_goals, behaviors, values, \
communication_style, and any other important information. For the AI, consider aspects such as short_term_goal, \
short_term_impression, and mood.

Only include categories that are explicitly mentioned or can be reasonably inferred from the dialogue. Exclude 
categories where no information is available or unknown. Provide detailed descriptions if needed to provide context.

Please format the output as 
{
"emotion": "xxx",
.....
}
Merge user and AI categories.'''

gen_question_answer = """Please generate at most {question_number} targeted questions for the summaries of chats between users so that the summaries contain information that can answer the question.
Questions should not include the names of specific people
Here are the raw text of chats summary:
{chat_summary}
Please response in json format:
{
"questions": []
}"""

get_target_timestamp = """### Task objective
Extract formatted time information from text input

### Output format
{
"formatted_time": "2023-12-26", # Year-Month-Day
"time_accuracy": "day", # enum: ['day', 'month', 'week', 'year', 'undefined']
}

### Field Interpretation
time_accuracy indicates the time range described by the user, e.g. when the user mentions last year, time_accuracy should be year, formatted_time should start with 2022, subsequent numbers are no longer important [but can't be omitted, must be kept intact]
If the user mentions a day in the last year, then accuracy should be day, no longer year.
If the user does not mention any time-related information, then formatted_time outputs the current time, and time_accuracy outputs 'undefined'.

### Task example

# Show Case 1.
Current time: 2023-12-27
Text input: Do you remember the wonderful Christmas we spend together last year?
Expected output.
{
"formatted_time": "2022-12-25",
"time_accuracy": "day"
}

# Show Case 2.
Current time: 2023-06-27
Text input: Do you remember the terrible car accident I talked about last year?
Expected output.
{
"formatted_time": "2022-06-27",
"time_accuracy": "year"
}

### Given conditions
The current system time is: {current_time}
The current user input is: {user_input}"""
#
# if __name__ == '__main__':
#     from datetime import datetime
#     import pytz
#
#     # 选择一个时区，例如 'Asia/Shanghai' 或 'America/New_York'
#     time_zone = pytz.timezone('America/New_York')
#
#     # 获取当前时间，并设置为指定时区的时间
#     current_time_in_timezone = datetime.now(time_zone)
#
#     # 格式化时间
#     formatted_time = current_time_in_timezone.strftime("%Y-%m-%d %H:%M:%S %Z")
#
#     print(formatted_time)