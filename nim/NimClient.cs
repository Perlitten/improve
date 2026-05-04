using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading.Tasks;

namespace NvidiaNimDemo
{
    public class NimClient
    {
        private static readonly HttpClient client = new HttpClient();
        private const string BaseUrl = "https://integrate.api.nvidia.com/v1/chat/completions";

        public async Task<string> GetChatCompletion(string apiKey, string userPrompt)
        {
            if (string.IsNullOrEmpty(apiKey))
                throw new ArgumentException("API Key is required");

            var request = new HttpRequestMessage(HttpMethod.Post, BaseUrl);
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

            // Payload for Llama 3.1 8B (OpenAI-compatible schema)
            var jsonBody = new
            {
                model = "meta/llama-3.1-8b-instruct",
                messages = new[] { new { role = "user", content = userPrompt } },
                temperature = 0.5,
                max_tokens = 1024,
                stream = false
            };

            string jsonString = System.Text.Json.JsonSerializer.Serialize(jsonBody);
            request.Content = new StringContent(jsonString, Encoding.UTF8, "application/json");

            var response = await client.SendAsync(request);
            response.EnsureSuccessStatusCode();

            return await response.Content.ReadAsStringAsync();
        }
    }

    class Program
    {
        static async Task Main(string[] args)
        {
            var nimClient = new NimClient();
            string apiKey = "nvapi-YOUR_KEY_HERE"; // Replace with your key
            
            Console.WriteLine("--- Calling NVIDIA NIM via C# ---");
            try 
            {
                var result = await nimClient.GetChatCompletion(apiKey, "Tell me about NVIDIA NIM.");
                Console.WriteLine(result);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex.Message}");
            }
        }
    }
}
