# NVIDIA NIM Quickstart Guide

This directory contains examples for integrating with **NVIDIA Inference Microservices (NIM)** via [build.nvidia.com](https://build.nvidia.com).

## Prerequisites

1.  **NVIDIA Account**: Sign up at [build.nvidia.com](https://build.nvidia.com).
2.  **API Key**:
    *   Navigate to a model card (e.g., [Llama 3.1 405B](https://build.nvidia.com/meta/llama-3_1-405b)).
    *   Click the **"Get API Key"** button.
    *   Copy the key (it starts with `nvapi-`).

## Files in this Directory

- `test_nim.py`: Python example using the `openai` library.
- `NimClient.cs`: C# example for .NET applications.
- `.env.example`: Template for environment variables.

## How to Run

### Python
1.  Install dependencies:
    ```bash
    pip install openai python-dotenv
    ```
2.  Copy `.env.example` to `.env` and paste your key.
3.  Run the script:
    ```bash
    python test_nim.py
    ```

### C# (.NET)
1.  Ensure you have a .NET project.
2.  Add the `OpenAI` NuGet package or use `HttpClient`.
3.  Reference `NimClient.cs` for logic.

## Common Models
- **Text**: `meta/llama-3.1-405b-instruct`, `nvidia/llama-3.1-nemotron-70b-instruct`
- **Vision**: `nvidia/neva-22b`, `meta/llama-3.2-11b-vision-instruct`
- **Audio**: `nvidia/parakeet-ctc-1.1b-asr`
