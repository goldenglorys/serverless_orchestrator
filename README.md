# Serverless Orchestrator

Serverless Orchestrator is a Python-based platform designed to orchestrate and manage serverless and edge functions hosted on Vercel. It enables seamless execution of these functions through cron jobs or webhook triggers, providing a flexible and efficient solution for various automation tasks.

## Features

- Deploy and manage Python serverless functions on Vercel
- Schedule function execution using cron jobs
- Trigger function execution via webhooks
- Seamless integration with Vercel's serverless infrastructure

## Setup

1. **Create a virtual environment (optional but recommended):**

   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

   Using a virtual environment helps keep your project's dependencies isolated and organized.

2. **Clone the repository:**

   ```
   git clone https://github.com/goldenglorys/serverless_orchestrator.git
   cd serverless_orchestrator
   ```

3. **Install dependencies:**

   ```
   pip install -r requirements.txt
   ```

4. **Configure Vercel:**

   - Install the Vercel CLI: `npm install -g vercel`
   - Link your Vercel account: `vercel login`

5. **Running Locally:**

    ```
    vercel dev
    ```

    Follow the prompts to configure your development settings.

6. **Deploy to Vercel:**

   ```
   vercel
   ```

   Follow the prompts to configure your deployment settings.

7. **Set up cron jobs or webhooks:**

   - For cron jobs, follow Vercel's documentation on [Scheduled Functions](https://vercel.com/docs/cron-jobs).
   - For webhooks, use the provided function URL as the endpoint for your webhook triggers.

## License

This project is licensed under the [MIT License](LICENSE).