import urequests
import json
import time
import WiFiManager

# Connect to Wi-Fi
# NOTE: On your host machine, start Ollama with:
# OLLAMA_HOST=0.0.0.0 ollama serve
WiFiManager.connect()

OLLAMA_IP = "192.168.2.5"  # Replace with your Computer's IP Address, example on a mac ifconfig | grep inet
OLLAMA_PORT = 11434
OLLAMA_URL = f"http://{OLLAMA_IP}:{OLLAMA_PORT}/api/generate"
OLLAMA_TAGS_URL = f"http://{OLLAMA_IP}:{OLLAMA_PORT}/api/tags"
OLLAMA_MODEL = "llama3"  # Default model

def get_available_models():
    """Get list of available models from Ollama"""
    try:
        response = urequests.get(OLLAMA_TAGS_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = [model.get('name', 'unknown') for model in data.get('models', [])]
            response.close()
            return models
        else:
            response.close()
            return []
    except Exception as e:
        print(f"Could not fetch models: {e}")
        return []

def select_model():
    """Let user select from available models"""
    print("Fetching available models...")
    models = get_available_models()
    
    if not models:
        print(f"Could not fetch models. Using default: {OLLAMA_MODEL}")
        return OLLAMA_MODEL
    
    print(f"\nAvailable models ({len(models)} found):")
    for i, model in enumerate(models, 1):
        default_marker = " (default)" if model == OLLAMA_MODEL else ""
        print(f"{i}. {model}{default_marker}")
    
    print(f"\nSelect model (1-{len(models)}) or press Enter for default ({OLLAMA_MODEL}):")
    
    try:
        choice = input().strip()
        
        if not choice:  # Empty input = default
            print(f"Using default model: {OLLAMA_MODEL}")
            return OLLAMA_MODEL
        
        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(models):
                selected_model = models[choice_num - 1]
                print(f"Selected model: {selected_model}")
                return selected_model
            else:
                print(f"Invalid choice. Using default: {OLLAMA_MODEL}")
                return OLLAMA_MODEL
        except ValueError:
            print(f"Invalid input. Using default: {OLLAMA_MODEL}")
            return OLLAMA_MODEL
            
    except Exception as e:
        print(f"Input error: {e}. Using default: {OLLAMA_MODEL}")
        return OLLAMA_MODEL

def ask_ollama(prompt_text):
    """Send a prompt to Ollama and get response"""
    headers = {"Content-Type": "application/json"}
    
    # Improve math prompts for better responses
    math_operators = ['+', '-', '*', '/', 'x', '=']
    is_math = any(op in prompt_text for op in math_operators)
    
    if is_math:
        prompt_text = f"Calculate this math problem and give only the answer: {prompt_text}"
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt_text,
        "stream": False,
        "options": {
            "temperature": 0.25,
            "num_predict": 250,
            "top_p": 0.9
        }
    }

    response = None
    try:
        print("Sending to Ollama...")
        response = urequests.post(OLLAMA_URL, headers=headers, data=json.dumps(payload), timeout=25)
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("response", "No response field in result.").strip()
            
            # Clean up math responses
            if is_math:
                lines = answer.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and (line.replace('.', '').replace('-', '').isdigit() or '=' in line):
                        return line
            
            return answer
        else:
            return f"HTTP Error {response.status_code}: {response.text[:100]}"
    except Exception as e:
        return f"Request failed: {str(e)}"
    finally:
        if response:
            try:
                response.close()
            except:
                pass

def main():
    """Main chat loop"""
    print("=== PicoCalc Ollama Chat ===")
    print(f"Connected to Ollama at {OLLAMA_IP}:{OLLAMA_PORT}")
    
    # Let user select model
    global OLLAMA_MODEL
    OLLAMA_MODEL = select_model()
    
    print("Model:", OLLAMA_MODEL)
    print()
    print("Instructions:")
    print("- Type your question/prompt and press Enter")
    print("- Type 'quit', 'exit', or 'q' to stop")
    print("- Type 'help' for example prompts")
    print("- Type 'models' to change AI model")
    print("========================================")
    
    while True:
        try:
            print("\nPrompt: ")
            prompt = input().strip()
            
            # Handle exit commands
            if prompt.lower() in ['quit', 'exit', 'q', 'bye']:
                print("Goodbye!")
                break
            
            # Handle empty input
            if not prompt:
                print("Please enter a prompt or 'quit' to exit.")
                continue
            
            # Handle help command
            if prompt.lower() == 'help':
                print("\nExample prompts:")
                print("- Math: 5 * 99, 15 + 23, 144 / 12")
                print("- Write a haiku about calculators")
                print("- Explain quantum physics simply")
                print("- Tell me a joke")
                print("- What's the capital of France?")
                print("- Solve this problem: ...")
                print("\nCommands:")
                print("- 'models' - Change AI model")
                print("- 'quit' - Exit the program")
                print("\nTips:")
                print("- For math, just type the calculation")
                print("- If response hangs, press Ctrl+C and try shorter prompts")
                continue
            
            # Handle model selection command
            if prompt.lower() == 'models':
                OLLAMA_MODEL = select_model()
                continue
            
            # Send to Ollama
            print("\n" + "-" * 30)
            response_text = ask_ollama(prompt)
            print("Ollama says:")
            print(response_text)
            print("-" * 30)
            
        except KeyboardInterrupt:
            print("\n\nChat interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\nError getting input: {e}")
            print("Type 'quit' to exit or try again.")

# Start the chat
if __name__ == "__main__":
    main()