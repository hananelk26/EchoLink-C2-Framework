'''
import requests


def main():
    print("=== EchoLink Operator Dashboard ===")
    # Prompt the user to enter the target agent ID
    agent_id = input("Enter Agent ID to target: ")

    # Start an interactive command loop
    while True:
        command = input(f"EchoLink@{agent_id} > ")
        if command.lower() in ['exit', 'quit']:
            break

        # Prepare the payload to send to the server
        payload = {"agent_id": agent_id, "command": command}

        try:
            # Send the command to the Flask server's add_task endpoint
            response = requests.post("http://127.0.0.1:5000/add_task", json=payload)

            if response.status_code == 200:
                print("[+] Task queued successfully.")
            else:
                # Parse the JSON response from the server to get the exact error
                error_data = response.json()
                error_message = error_data.get("message", "Unknown error occurred")
                print(f"[-] Failed to queue task. Reason: {error_message}")

        except Exception as e:
            print(f"[-] Error connecting to server: {e}")


if __name__ == '__main__':
    main()
'''

import requests
import time


def main():
    print("=== EchoLink Operator Dashboard ===")
    agent_id = input("Enter Agent ID to target: ")

    while True:
        command = input(f"EchoLink@{agent_id} > ")
        if command.lower() in ['exit', 'quit']:
            break

        payload = {"agent_id": agent_id, "command": command}

        try:
            # 1. Send the command to the queue
            response = requests.post("http://127.0.0.1:5000/add_task", json=payload)

            if response.status_code == 200:
                print("[*] Task queued. Waiting for agent execution...")

                # 2. Polling loop: Wait for the agent to fetch, execute, and return results
                max_retries = 15  # Wait for up to 30 seconds (15 tries * 2 sec delay)
                retries = 0
                result_found = False

                while retries < max_retries:
                    time.sleep(2)  # Delay to avoid flooding the server with requests

                    # Ask the server if results are available yet
                    res_response = requests.get(f"http://127.0.0.1:5000/get_results/{agent_id}")

                    if res_response.status_code == 200:
                        res_json = res_response.json()

                        # If the server has the result, print it and break the waiting loop
                        if res_json.get("status") == "success":
                            print("\n[+] Command Output:\n" + "=" * 40)
                            print(res_json.get("output", ""))
                            print("=" * 40 + "\n")
                            result_found = True
                            break

                    retries += 1

                # If the loop finished without finding results, notify the operator
                if not result_found:
                    print("[-] Timeout: Agent did not return results within 30 seconds.")

            else:
                error_data = response.json()
                error_message = error_data.get("message", "Unknown error occurred")
                print(f"[-] Failed to queue task. Reason: {error_message}")

        except Exception as e:
            print(f"[-] Error connecting to server: {e}")


if __name__ == '__main__':
    main()