import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup the NVIDIA NIM client
# Note: NVIDIA NIM is OpenAI-compatible
client = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key=os.getenv("NVIDIA_API_KEY")
)

def get_completion():
    if not os.getenv("NVIDIA_API_KEY"):
        print("Error: NVIDIA_API_KEY not found in environment variables.")
        print("Please check your .env file.")
        return

    print("--- Calling NVIDIA NIM (Llama 3.1 8B) ---")
    
    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[{"role":"user","content":"Explain how NVIDIA NIM works in 1 short sentence."}],
            temperature=0.5,
            top_p=1,
            max_tokens=100,
            stream=False
        )

        print(completion.choices[0].message.content)
        print("\n-------------------------------------------")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    get_completion()
