# FortyTwo MCP Agent

An autonomous agent bot that integrates with the [Fortytwo Network](https://fortytwo.network) via the **MCP (Model Context Protocol)** standard. It monitors the Mineloot game for new rounds and queries the `ask_fortytwo_prime` AI tool, paying per query using **USDC on the Base blockchain** via the **x402 payment protocol**.

## Features

- 🤖 **Autonomous loop** — polls Mineloot API for new game rounds
- 💡 **AI-powered** — sends grid data to Fortytwo Prime for strategy suggestions
- 💳 **x402 payments** — signs EIP-712 `ReceiveWithAuthorization` for gasless USDC escrow
- 💰 **Budget control** — daily spend cap + per-call cooldown
- 🔌 **Skills system** — extensible plugin folder for additional MCP skills

## Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/YOUR_USERNAME/fortytwo-agent.git
   cd fortytwo-agent
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure credentials**
   ```bash
   cp .env.example .env
   # Edit .env and fill in your values
   ```

4. **Run the agent**
   ```bash
   python agent.py
   ```

## Configuration (`.env`)

| Variable | Description |
|---|---|
| `evm_private_key` | Your EVM wallet private key (used to sign x402 payments) |
| `MY_WALLET_ADDRESS` | Your wallet address |
| `ANTHROPIC_API_KEY` | Anthropic API key (optional, for local Claude integration) |
| `BASE_RPC_URL` | Base mainnet RPC URL (default: `https://mainnet.base.org`) |

> ⚠️ **Never commit your `.env` file.** It is listed in `.gitignore`.

## Cost

- Escrow per call: ~$2.00 USDC (refunded to ~$0.50 net cost)
- Default daily budget: **$5.00 USDC**
- Default cooldown between calls: **30 minutes**

## Skills

Additional MCP skills can be added to the `skills/` directory. Currently installed:
- `fortytwo-mcp` — [Fortytwo-Network/fortytwo-mcp-skills](https://github.com/Fortytwo-Network/fortytwo-mcp-skills)

## License

MIT
