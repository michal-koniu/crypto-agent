# B — DeFi toolkits, wallet/signer design, execution venues, BTC exposure, yield, risk checks, fork testing

Research date: **2026-10-29**. "Verified" means checked on that date against a live source: the GitHub REST API (`gh api`), the npm/PyPI registries, a live API call made from this machine, a public RPC `eth_call`, or the official docs page cited. Anything marked **(memory)** or **(unverified)** was not confirmed live and needs a re-check before it is relied on.

Context: the agent aims to beat a buy-and-hold BTC benchmark. It trades at low frequency. An LLM proposes actions, a deterministic policy engine approves them, and a separate signer signs. Keys never reach the LLM. The starting wallet holds ~100 USDT on an L2 and may grow to ~5,000. All testing happens on Anvil forks or testnets.

---

## 0. Executive summary

| Area | Recommendation | One-line reason |
|---|---|---|
| Agent toolkit | **No full framework.** Build a thin Python (web3.py 8 / eth-account 0.14) or TS (viem) stack. Use **karpatkey DeFi Kit + zodiac-roles-sdk** for permissions, and **Almanak SDK** / **Coinbase AgentKit** only as reference adapters. | Every framework co-locates keys with the agent runtime or is stale or archived. The policy-engine/signer split is easier to keep clean when you own the code. |
| Wallet | **Safe (1/1, owner = hardware wallet) + Zodiac Roles Modifier v2.** The agent "executor" EOA is a role member, not an owner. | Limits are enforced on-chain, so a stolen hot key can only do what the role allows. The contracts are audited (G0, Omniscia) and deployed at the same address on Base and Arbitrum. Cost is cents on L2. |
| Signer | Local **signer daemon** holding an **eth-account encrypted keystore** in its own process and OS user. Optionally move the executor key to **CDP Server Wallet** (TEE, 5k free ops/mo) or **Privy** (TEE with cumulative-limit policies) at the $5k stage. | The on-chain role is the real limit. A vendor policy only adds defence in depth. |
| Kill switch | (a) Signer/policy kill flag. (b) A cold owner revokes the role or disables the module. (c) A separate **"exit" role** that can only withdraw from lending, cancel orders, zero approvals and `transfer(to == COLD_ADDRESS)`. | The exit role can be hot (watchdog) because it cannot send funds anywhere except the cold address. |
| Chain | **Base.** | Live data: cbBTC supply on Base is **48,583 BTC** versus 66 on Arbitrum. The main USDC vaults are on Base. CoW and UniswapX are live on Base. honeypot.is supports Base. |
| BTC leg | **cbBTC on Base.** | Deepest L2 BTC liquidity. The custodian is Coinbase, which is a centralized, freeze-capable issuer and an accepted risk. |
| Execution | **CoW Protocol API** as the primary venue, with **Velora (ParaSwap)** and **KyberSwap** quotes as cross-checks. 0x, 1inch and Uniswap need API keys. **Odos is shut down** (July 30, 2026). | CoW's quote returns the network fee, protocol fee bps and a `verified` (simulated) flag. Batch auctions protect against MEV. Limit orders are native. DeFi Kit already has a Roles preset that forces `receiver == Safe`. |
| Stop-loss | Run it in the agent's own deterministic monitor, and use CoW limit orders for entries and take-profits. Don't depend on Gelato: a competitor reports Web3 Functions reached EOL on 2026-03-31. | At low frequency, a self-run monitor is simpler and more reliable than keeper networks. |
| Yield | Stablecoins in a **Morpho USDC vault on Base** (Steakhouse, Gauntlet or Spark, about 5.5–6.8% now, 30-day averages 4.2–5.8%) or Aave v3 Base USDC (6.2%, but **91% utilization**). **BTC lending yield on L2 is about 0%**: Aave cbBTC 0.01%, Aave Arbitrum WBTC 0.02%. | Against a BTC benchmark, stablecoin yield is a short-BTC position with a coupon. No lending product earns meaningful yield on BTC on these L2s. |
| Risk data | GoPlus (free, no key), honeypot.is (**Base only**, Arbitrum rejected), DefiLlama yields, lendBorrow and hacks (free), Etherscan V2 (**Base needs a paid plan**; Arbitrum is free; source/ABI is free on all chains). | All of these were tested live. |
| Fork testing | **Foundry Anvil v1.8.7** with a pinned fork block on an **archive** RPC (Alchemy free tier, 30M CU/mo). `mainnet.base.org` served archive state. `arb1.arbitrum.io` did not. | Lazy state fetches at a pinned block fail on pruned nodes. |

---

## 1. Agent DeFi toolkits

### 1.1 Maintenance and metadata (all verified 2026-10-29 via GitHub API, npm and PyPI)

| Project | Repo (current owner) | Stars | License | Last default-branch commit | Commits since 2026-07-29 | Latest package | Language | Status |
|---|---|---|---|---|---|---|---|---|
| Coinbase AgentKit | coinbase/agentkit | 1,346 | Apache-2.0 (npm; GH shows NOASSERTION) | 2026-10-14 | 5 | npm `@coinbase/agentkit` 0.10.4 (2025-12-19); PyPI `coinbase-agentkit` 0.7.4 (2025-10-03); nightlies stopped 2026-02-01 | TS + Python | **Maintenance mode.** Fixes only. Recent commits include "document inherent prompt injection risk" (#1433) and "sanitize erc20 token metadata" (#1480). |
| GOAT SDK (Crossmint) | goat-sdk/goat | 1,014 | MIT | 2026-07-02 (README only); last code 2025-08-19 | 0 | `@goat-sdk/core` 0.5.0 (2025-05-13) | TS + Python | **Archived.** The README says "read-only historical snapshot… no longer actively maintained". |
| ElizaOS | elizaOS/eliza (branch `develop`) | 19,713 | MIT | 2026-10-29 | 100+ | `@elizaos/core` 1.7.2 (2026-01-19), `2.0.0-alpha.*` | TS | Very active, but **`elizaos-plugins` org now has 0 public repos**. The `plugin-evm` repo link returns 404. `@elizaos/plugin-evm` latest is 1.0.13 (2025-09-08) and alpha 2.0.0-alpha.8 (2026-04-06). |
| Olas / Autonolas | valory-xyz/open-autonomy | 135 | Apache-2.0 | 2026-10-26 | 16 | open-autonomy 0.21.30 (2026-10-26); olas-operate-middleware 0.15.48 (2026-10-29) | Python | Active. The `valory-xyz/optimus` DeFi agent was pushed today, and the Pearl app is active. The old `*-quickstart` repos are archived. |
| Brian | brian-knows/brian-sdk | 8 | MIT | 2025-01-24 | 0 | `@brian-ai/sdk` 0.3.7 (2025-01-24) | TS | **Shut down.** RootData reported termination of operations on 2025-05-26. |
| Virtuals GAME | game-by-virtuals/game-python, game-node | 100 / 93 | MIT | 2025-10-01 / 2026-03-06 | 0 | `@virtuals-protocol/game` 0.1.14 (2025-04-21) | Py / TS | Stale. Virtuals' activity has moved to ACP/"Butler" skills, and `Virtual-Protocol/acp-node` is archived. |
| Hey Anon | no public SDK repo found | – | – | – | – | – | – | Token/DAO-centric product. A DAO merger proposal with WAGMI was reported 2026-07-20. **Couldn't verify any open SDK.** |
| Wayfinder Paths SDK | WayfinderFoundation/wayfinder-paths-sdk | 24 | MIT | 2026-10-28 | 60 | PyPI `wayfinder-paths` 0.11.1 (2026-09-09) | Python 3.12 | Active. Ships an MCP server for Claude Code. |
| **Almanak SDK** (2025–26 entrant) | almanak-co/sdk | 62 | Apache-2.0 | 2026-10-09 | 100+ | PyPI `almanak` 3.1.0 (2026-10-28) | Python | Very active. Intent-based design with an Anvil paper-trading mode. |

Other 2025–26 entrants seen but **not evaluated**: World Liberty "AgentPay SDK" (CLI + local signing daemon + policy engine), PolicyLayer, Cobo Agentic Wallet (commercial), and various ETHGlobal hackathon projects (source: https://www.spark.money/research/ai-agent-wallet-policy-architecture, https://www.cobo.com/ae/post/ai-wallet-guide-intelligent-crypto-wallets). Treat them as early-stage.

### 1.2 What each does, how it handles keys, and how well it fits an external policy engine

| Toolkit | What it actually does | Key/security model | Fit for LLM → policy engine → signer |
|---|---|---|---|
| **AgentKit** | "Action providers" (ERC-20, swap, Morpho, Pyth, etc.) exposed as LLM tools, plus "wallet providers" (CDP Server Wallet, viem, Privy, Smart Wallet). | Keys sit with the wallet provider. With the CDP provider they are in Coinbase's TEE and CDP policies apply. With viem the key is in-process. | **Medium.** You can write a custom `WalletProvider` that forwards unsigned txs to your policy engine. Action encoders are reusable. Development is slowing, so pin versions and vendor the code you use. |
| GOAT | 200+ tool plugins and wallet adapters. | In-process wallet clients. | **Don't use.** It is archived. |
| ElizaOS | A full agent OS (characters, memory, social clients). Wallet actions come through plugins. | The EVM plugin reads `EVM_PRIVATE_KEY` from the agent's environment (memory), so the key lives in the same process as the LLM runtime. | **Poor.** It conflicts with "keys never reach the LLM", the DeFi plugins have been moved or re-org'd, and it is very heavy. |
| Olas | Autonomous-service framework: an FSM app on Tendermint consensus. Agents operate a Safe owned by agent-instance keys. Optimus/Modius are DeFi portfolio agents, and staking earns OLAS. | The agent runtime holds its instance key(s), and the Safe is owned by them. | **Low–medium.** It is robust but overbuilt for one operator. The Optimus strategies are worth reading as a reference. |
| Brian / GAME / Hey Anon | NL→tx APIs, game/social agents, token-driven DeFAI. | – | **Not viable.** They are dead, stale, or closed. |
| Wayfinder Paths | Python strategies and adapters (Moonwell, Hyperliquid, Polymarket, Boros), an MCP server, and a vendor fork service ("Gorlami"). | **`private_key_hex` / `wallet_mnemonic` are stored in `config.json`**, readable by the same process that serves MCP tools to Claude. Remote Privy wallets are also an option. Uses a vendor API key and proxy RPC. | **Low as delivered.** It breaks key isolation unless you strip the signing out. The adapters are usable as a reference. |
| **Almanak** | Intent framework (Swap/LP/Borrow…), 19 chains and 46 connectors, backtester, Anvil paper trading, and an LLM agent with "41 tools and policy-enforced safety". | README: a **gateway sidecar holds all secrets** (keys, API keys) behind gRPC, strategy code can't read them, the design is **Safe + Zodiac Roles Modifier**, and agent EOA keys are encrypted. | **Best architectural match** to the target design. Caveats: young, vendor-linked, and I did not verify whether the "managed gateway" phones home. Use it as a reference or for parts, and audit before trusting. |

Sources:
- https://github.com/coinbase/agentkit
- https://github.com/goat-sdk/goat
- https://github.com/elizaOS/eliza
- https://github.com/valory-xyz/open-autonomy
- https://www.rootdata.com/news/284004 (Brian shutdown)
- https://cryptobriefing.com/heyanon-token-triples-equilibra-robinhood-chain/
- https://github.com/WayfinderFoundation/wayfinder-paths-sdk
- https://github.com/almanak-co/sdk

### 1.3 Library-level notes (verified)
- **web3.py and eth-account now live under the ApeWorX org.** `ethereum/web3.py` and `ethereum/eth-account` redirect to `ApeWorX/web3.py` and `ApeWorX/eth-account`. Both are active: web3 8.0.0 (2026-08-31), eth-account 0.14.0 (2026-08-23), MIT. I found no official announcement of the transfer (unverified).
- viem 2.57.13 (2026-10-28) and `@safe-global/protocol-kit` 8.0.11 (2026-10-28) are both active. Safe's GitHub org is now **safe-fndn**.
- **karpatkey/defi-kit** (MIT, pushed 2026-10-26) ships ready-made Zodiac Roles permission presets for **CoW Swap, Uniswap, Aave, Morpho, Compound, Fluid and Spark**, including Arbitrum and Base CoW pages. The CoW preset routes through an `orderSigner.signOrder` delegatecall with `receiver: c.avatar`, so the agent cannot sign an order that pays someone else. This is the key building block for the policy layer: https://github.com/karpatkey/defi-kit

---

## 2. Signing and key infrastructure

### 2.1 Options compared

| Option | Where the limit is enforced | What it can restrict | Maturity (verified) | Cost on Base/Arb | Verdict for $100–$5k |
|---|---|---|---|---|---|
| Plain EOA + eth-account keystore | Only your off-chain code | Whatever your signer checks | Mature | ~0 | OK for the $100 phase **only** if a total loss is acceptable. A leaked key means everything is gone. |
| **Safe + Zodiac Roles v2** | **On-chain** | Target, function and **parameter** conditions (e.g. `recipient == avatar`), call/delegatecall/send, plus rate and threshold limits ("allowances") on parameters | Roles v2 is in production at `0xF2964CE6161ce0e75964Fe7927cE114cb0B283D5` on **Arbitrum One and Base** (and others). Audits by **G0 Group and Omniscia**. Roles v3 is not yet released. `zodiac-roles-sdk` 4.1.5 published 2026-10-26. | Safe deploy plus module setup is a few cents. Roughly +30–60k gas per call (memory). | **Recommended.** |
| Safe Allowance Module | On-chain | **Only token/ETH transfers** to arbitrary recipients up to a recurring allowance. Cannot scope swaps or deposits. | `allowances/v1.0.0` released 2026-02-25 | cents | Too narrow for trading. Could serve as a "pocket money" mechanism. |
| ERC-7579 Smart Sessions (Rhinestone) | On-chain (4337) | Session keys with policies (spend/value/time/usage/param rules) | Audits in repo: ChainLight, Cantina ×2, plus 2 others. **erc7579/smartsessions last commit 2025-08-04**, and **ModuleKit is marked "No longer maintained"** in favour of the Rhinestone SDK. | Needs a bundler, plus a paymaster or ETH | Solid tech but more infrastructure (bundler) and uncertain repo maintenance. Second choice. |
| ZeroDev Kernel | On-chain (4337/7702) | Permissions = signer + policies (call policy with params, gas, rate-limit, timestamp, signature) | **Kernel v4 was released 2026-10-05.** Its release PR "remove audit changelog and audit folder"; v3.3 dates from 2025-04. `@zerodev/sdk` 5.5.11 (2026-10-16). | bundler / paymaster | Too new to trust with funds. If used, pin audited v3.x. |
| Biconomy Nexus | On-chain (4337/7579) | via modules | v1.2.0 (2025-04-07). 1 commit since July 2026. | bundler | Slow-moving. |
| Alchemy Modular Account v2 | On-chain | session keys / permissions | v2.0.0 (2025-03-18). Last commit 2025-12-19. | bundler | Slow-moving. |
| EIP-7702 (EOA → smart code) | On-chain, but **the EOA key remains omnipotent** | Same as the delegated account (e.g. `Kernel7702`) | Live on Arbitrum since ArbOS 40 (activation 2025-06-17) and live on Base (growthepie: Base leads in 7702 tx count, ~747k per 30 days as of 2026-05). Trail of Bits noted Arbitrum precompiles deviate from 7702 when delegated to. | ~0 | **No security gain** unless the EOA root key is itself cold. The root can't be rotated, and malicious-delegation phishing is a known risk. Not recommended as the primary design. |
| **CDP Server Wallet v2** | Coinbase TEE (AWS Nitro Enclaves) | Verified criteria: `ethValue`, `evmAddress` (in/not-in). Reject beats accept. Project and account scopes. | Active (`@coinbase/cdp-sdk` 1.60.0, 2026-10-22) | **$0.005 per write op, first 5,000 ops/month free.** One older page says 500, so check your account. A send counts as 2 ops, and policy evaluation is billed as 1. | Good optional second layer. **Unverified:** calldata/param and cumulative-spend criteria. |
| **Turnkey** | Secure enclave | `eth.tx.{to,data,value,chain_id,…}`, `function_name`, `contract_call_args` (requires an uploaded ABI), time windows. **No cumulative spend limits.** | Active (`@turnkey/sdk-server` 8.8.0, 2026-10-24) | 25 free signatures/month, then **$0.10 per signature**. Pro is $99/mo + $0.05. | Expensive per signature at hobby scale. |
| **Privy server wallets** | TEE | Allow/deny lists, ABI-decoded calldata rules, EIP-712 field rules, time fields, and **stateful aggregated limits** (e.g. cumulative value over a time window, for `eth_signTransaction` / `eth_signUserOperation`) | Active (`@privy-io/node` 0.37.0, 2026-10-26). Acquired by Stripe in 2025 (memory). | Pricing not verified | The strongest off-chain policy language of the vendors. |
| Lit Protocol / Vincent | Lit network | Spend limits and token allowlists per "ability" | **In network migration v0→v1** (Lit blog, 2025-11-10). `LIT-Protocol/Vincent` last push 2026-01-31. `lit-peer` archived 2026-09-16. | ? | Avoid: platform churn. |
| Fireblocks | MPC + TAP policy engine | Rich | Mature | Enterprise pricing (not verified) | Overkill for $5k. |

Sources:
- https://github.com/zodiaceco/zodiac-modifier-roles-v2 (deployments and audits)
- https://github.com/zodiaceco/zodiac-modifier-roles (v3 not released)
- https://docs.roles.gnosisguild.org/
- https://github.com/safe-fndn/safe-modules/tree/main/modules/allowances
- https://github.com/erc7579/smartsessions/tree/main/audits
- https://github.com/rhinestonewtf/modulekit
- https://github.com/zerodevapp/kernel/releases/tag/v4.0
- https://docs.zerodev.app/sdk/permissions/intro
- https://tally.xyz/gov/arbitrum/proposal/13108804573775967668959825241666341617107666532012387058509418598838035461528
- https://www.growthepie.com/answers/most-smart-account-activity-ethereum-l2
- https://docs.arbitrum.io/assets/files/2025-05-Offchain-Labs-ArbOS-40-Nitro-Summary-Report-769a942c08fe0f917eef523cba81a459.pdf
- https://docs.cdp.coinbase.com/server-wallets/v2/using-the-wallet-api/policies/overview
- https://docs.cdp.coinbase.com/server-wallets/v2/introduction/pricing
- https://docs.turnkey.com/features/policies/language
- https://www.turnkey.com/pricing
- https://docs.privy.io/controls/policies/overview
- https://spark.litprotocol.com/v1-and-next-phase/

Relevant incidents (DefiLlama hacks DB, verified):
- **Bankr** (Base), "Session Key Compromised", $170k, 2026-05-19, plus a second Bankr entry on 2026-07-25.
- **SquidRouterModule** (Ethereum, Base), "Improper Access Control", $3.2M, 2026-05-04.
- Approval-abuse losses in 2026: Aperture $3.67M, Gondi, Ekubo, ZetaChain, and Limit Break.

The lesson: module and session-key setups only protect you if the scoping is tight, and approvals need hygiene.

### 2.2 Recommended design

```
 ┌──────────┐   proposal (JSON intent)   ┌──────────────────────┐  approved unsigned tx + approval sig  ┌──────────────────┐
 │   LLM    │ ─────────────────────────▶ │ Policy engine (det.) │ ─────────────────────────────────────▶│  Signer daemon   │
 │ (no keys,│                            │ - allowlist/limits   │                                        │ separate OS user │
 │  no RPC  │ ◀── result / rejection ─── │ - oracle price check │                                        │ keystore (scrypt)│
 │  write)  │                            │ - Anvil fork sim     │                                        │ re-checks to/sel │
 └──────────┘                            │ - GoPlus/token checks│                                        └────────┬─────────┘
                                         └──────────────────────┘                                                 │ execTransactionWithRole
                                                                                                                  ▼
                       Cold owner (hardware wallet) ──owns──▶  SAFE (holds ALL funds)  ◀──module── Zodiac Roles v2
                                                                                                   ├─ role AGENT  : executor EOA
                                                                                                   └─ role EXIT   : watchdog EOA
```

1. **Safe v1.4.1 or v1.5.0 on Base.** Threshold 1. Sole owner = a hardware-wallet address. The executor EOA is **not** an owner. Funds live only in the Safe. The executor EOA holds about $1 of ETH for gas.
2. **Roles Modifier v2** enabled as a Safe module. Role **AGENT** is built from DeFi Kit presets:
   - `cowSwap.swap({sell:[USDC,cbBTC], buy:[USDC,cbBTC]})`, which forces `receiver = avatar`.
   - Approvals to the GPv2VaultRelayer, scoped to the allowlisted tokens only.
   - `aave_v3` or `morpho` deposit/withdraw with `onBehalfOf / receiver = avatar`.
   - No `transfer`, no `delegatecall` except the DeFi Kit order signer, and no module or owner management.
   - Add Roles **allowances** (rate limits) on sell amounts. For example, at most 25% of NAV per 24 h, with the cap set in token units and refreshed by the owner.
3. **Role EXIT** is assigned to a separate watchdog key, which can be hot (a different machine or phone). It may only:
   - withdraw from the lending protocols to the avatar;
   - cancel CoW orders (`invalidateOrder` / `setPreSignature(uid,false)`);
   - `approve(spender, 0)`;
   - `transfer(to == COLD_ADDRESS)` / ETH send to `COLD_ADDRESS`.

   Even if this key is compromised, the worst case is "funds moved to my cold wallet".
4. **Kill switch, three layers.**
   1. *Soft:* the policy engine sets a halt flag, and the signer refuses all non-EXIT actions. It also refuses to sign when its heartbeat to the policy engine is lost.
   2. *Exit:* the watchdog runs the EXIT batch: cancel orders, unwind lending, zero approvals, sweep to `COLD_ADDRESS`. Triggers: drawdown versus BTC beyond a threshold, oracle deviation, an unknown approval or tx seen from the Safe, or a manual button.
   3. *Hard:* the cold owner sends `assignRoles(executor,[AGENT],[false])` or `disableModule(Roles)`. That single tx makes the hot keys powerless, and funds stay in the cold-owned Safe.
5. **Signer daemon** (Python with eth-account, or TS with viem):
   - loads the keystore once and runs as its own Unix user;
   - exposes only `sign(approved_tx, approval_sig)`;
   - verifies the policy engine's ed25519 approval over the exact tx hash;
   - re-checks `to ∈ {RolesModifier}`, the selector, and that `chainId == 8453`;
   - keeps an append-only audit log.

   The LLM process gets no RPC write access and no filesystem access to the keystore.
6. **Optional at $5k:** move the executor key into **CDP Server Wallet** (cheap: 5k free ops per month) or **Privy** (cumulative limits) so that a host compromise still faces a vendor policy. This is defence in depth, not a replacement for Roles.
7. **Phase-0 shortcut ($100):** a plain EOA with off-chain policy only is acceptable if a total loss of $100 is acceptable. The Safe + Roles path costs only cents in gas, though, and it is the thing you need to test on forks anyway, so starting with it avoids a migration.

Funding note: there is **no USDT pool on Base** in DefiLlama's dataset, and Base's stable liquidity is USDC. Convert USDT to USDC on the exchange and withdraw USDC on Base. If funding on Arbitrum instead, USDT0 is the Tether asset there; I did not verify its address.

---

## 3. Execution venues on Arbitrum and Base

### 3.1 Aggregators: does the API return all-in cost before execution?

Live test on 2026-10-29: sell 100 USDC for cbBTC on Base (chain 8453).

| Venue | Key needed? | Result / cost fields returned pre-trade | Notes |
|---|---|---|---|
| **CoW Protocol** `POST api.cow.fi/base/api/v1/quote` | **No** | `buyAmount` 123,386 sats. `feeAmount` 8,352 (≈ **$0.0084** network cost, in sell token). `gasAmount`, `gasPrice`. **`protocolFeeBps: "2"`**. **`verified: true`** (solver-simulated). `validTo`. | MEV protection via batch auction with uniform clearing price. Gasless for the user. Supports limit orders (`partiallyFillable`), TWAP, and ComposableCoW conditional orders. Supported on Arbitrum and Base. **Incidents:** CoW Swap DNS hijack on 2026-04-14 ($1.2M, frontend), plus solver/settlement incidents in 2023 and 2024 ($180k, $59k). Use the API, not the UI. |
| **Velora (ParaSwap)** `GET api.paraswap.io/prices` | No | `destAmount` 123,409 sats. **`gasCostUSD` $0.00478**. `srcUSD` 99.95 / `destUSD` 99.96, from which price impact can be derived. `partnerFee` 0.01. | ParaSwap had a $300k access-control incident in 2024-03. |
| **KyberSwap** `GET aggregator-api.kyberswap.com/base/api/v1/routes` | Only the `x-client-id` header | `amountOut` 123,347. `amountInUsd` / `amountOutUsd`. **`gasUsd` $0.0077**. `extraFee`. | KyberSwap Elastic hack in 2023-11 ($48M, Base and Arbitrum among the chains). |
| **0x Swap API v2** | **Yes**. Without one: "No API key found". Pay-per-request via x402 on Base is offered as an alternative. | Per docs: `fees.{integratorFee, zeroExFee, gasFee}`, `gas`, `gasPrice`, **`totalNetworkFee`**, `minBuyAmount`, **`issues.{allowance, balance, simulationIncomplete}`**, `route`, `tokenMetadata` (buy/sell tax). | **`zeroExFee` is charged** (the docs sample shows it on a DAI trade). No explicit price-impact field in the sample. |
| **1inch Swap / Fusion** | **Yes** (`Unauthorized` without one). Free dev tier reported at 1 rps and 100k calls/mo; paid from $199/mo (third-party, checked 2026-07-08). | Quote returns `dstAmount` and a gas estimate (memory). Fusion is intent-based, gasless and resolver-filled. | 1inch Fusion v1 resolver exploit 2025-03 ($5M); 1inch frontend supply-chain attack 2024-10. limit-order-protocol 4.3.4 released 2026-09-24. Fusion SDK pushed 2026-10-20. |
| **Uniswap Trading API** | **Yes** | Classic quotes include gas-fee USD and price impact (memory, not re-verified). UniswapX V2 and V3 are both **live on Arbitrum and Base**. Universal Router 2.1.2 is at `0xd6145b2D…9c40` (Base) and `0x2d014117…Fe65` (Arbitrum). | **UniswapX has a per-chain minimum quote value.** Below it, a UniswapX route is only offered if it beats the AMM by ≥0.2%, otherwise the API returns 404 `QuoteAmountTooLowError`. That excludes $100 trades in practice. One page cites a 300 USDC minimum; I did not confirm the per-chain values. |
| **Odos** | – | **Service retired 2026-07-30.** `api.odos.xyz` returns Cloudflare error 1033 (tested). | Do not integrate. |

**Conclusion:** none of these APIs returns a single "all-in" number that includes price impact relative to a fair price. CoW is the closest: its `feeAmount` and `protocolFeeBps` are inside the quoted amount, and it is simulation-verified. The policy engine should compute all-in cost itself:

`cost_bps = 1 − (out_amount × oracle_price_out) / (in_amount × oracle_price_in)`

using an independent oracle (e.g. Chainlink cbBTC/USD on Base) plus the gas in USD. Compare against at least two venues, and **re-simulate the exact calldata on an Anvil fork** before signing.

At $100–$5k on Base, explicit costs are tiny: about $0.005–0.01 gas and 2 bps CoW protocol fee. The quotes from three venues were within 0.05% of each other.

Sources:
- https://docs.cow.fi/
- https://api.cow.fi
- https://docs.0x.org/docs/introduction/quickstart/swap-tokens-with-0x-swap-api.md
- https://docs.0x.org/llms.txt
- https://www.mintlify.com/1inch/fusion-sdk/concepts/networks
- https://comparedge.com/tools/1inch
- https://developers.uniswap.org/docs/trading/swapping-api/supported-chains.md
- https://www.kucoin.com/news/flash/odos-protocol-to-wind-down-dex-aggregator-users-must-withdraw-funds-by-july-30
- https://en.coin-turk.com/odos-to-end-all-defi-aggregator-services-on-july-30-users-warned-to-secure-assets/

### 3.2 MEV on L2s
- **Arbitrum:** first-come-first-served sequencer plus **Timeboost** express-lane auction, live on Arbitrum One since **2025-04-17**. The express lane gives a time advantage for backrunning and arbitrage. Sandwiching is hard because the mempool is private (https://docs.arbitrum.io/how-arbitrum-works/timeboost).
- **Base:** private sequencer mempool, priority-fee ordering, and **Flashblocks** (200 ms) since **July 2025** (https://www.theblock.co/news/ecosystems/2025-07-17-coinbase-base-flashblocks-363109).
- Research:
  - *"How to Serve Your Sandwich? MEV Attacks in Private L2 Mempools"* (arXiv 2601.19570, 2026-01-27) finds sandwiching "rare, unprofitable, and largely absent" in private-mempool rollups (https://arxiv.org/abs/2601.19570).
  - *"No Place to Hide"* (arXiv 2609.28115, 2026-09-23) nevertheless measured **1,889 sandwiches on Base protected flow**, attributed to an **RPC bug exposing pending txs** plus predictable victim behaviour (https://arxiv.org/abs/2609.28115).
  - A secondary report describes a ~$500k loss on Base (2026-08) from a swap with no slippage protection (https://blockchain.news/flashnews/base-attacker-drains-500k-usdc-via-mev-sandwich).
- **Policy:** always set a tight `minOut` (for example ≤30 bps from the oracle-derived expectation at this size). Prefer CoW, where batch settlement gives MEV protection. Never send swaps with a zero minimum.

### 3.3 Limit and stop-loss options

| Mechanism | Chains | How it fills | Reliability notes |
|---|---|---|---|
| **CoW limit orders** | Arbitrum, Base | Off-chain signed or presigned. Solvers fill when the price is reachable. Gasless. Supports `validTo` expiry and partial fills. | Good for entries and take-profits. Depends on solver interest, which is fine for liquid pairs like USDC/cbBTC. |
| **CoW ComposableCoW** (TWAP, oracle stop-loss) | Arbitrum, Base (same `0xfdaFc9d1…3b74` reported) | Conditional orders validated via ERC-1271. Needs a Safe with the ExtensibleFallbackHandler, and a **watch-tower** that posts orders. | Stop-loss relies on a Chainlink feed and the watch-tower service. Audited by Ackee. TWAP for EOAs was announced in 2026. Third-party docs only; verify addresses on the explorers. |
| **1inch limit orders v4** | Arbitrum, Base | Resolvers/takers fill | Needs an API key to post to their orderbook. |
| **UniswapX** | Arbitrum, Base | Dutch / RFQ fillers | Minimum order size makes it unsuitable at $100. |
| **Gelato Web3 Functions** | – | Keeper | **Reported end-of-life 2026-03-31.** The only source is a competitor (KeeperHub) and there is no official Gelato notice; the automate-sdk was last published 2025-04. Don't build on it. |

**Recommendation:** the agent's own deterministic monitor (low-frequency cron plus price oracle) owns stop-loss logic and executes through the normal policy → signer path. Use CoW limit orders for resting entries and exits. Optionally add ComposableCoW stop-loss as a **backup** only after fork-testing the watch-tower behaviour.

Sources:
- https://github.com/cowprotocol/composable-cow
- https://www.mintlify.com/cowprotocol/composable-cow/deployment/networks
- https://docs.keeperhub.com/guides/gelato-migration

---

## 4. BTC exposure on L2

On-chain `totalSupply()` read via public RPC on 2026-10-29:

| Token | Address | Base supply | Arbitrum supply | Issuer / custody model | Key risks / incidents |
|---|---|---|---|---|---|
| **cbBTC** | `0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf` (both chains) | **48,582.59** | 66.26 | Coinbase-custodied. Centralized mint/burn. Upgradeable proxy (GoPlus `is_proxy=1`), owner `0x42d9…c2af`. | Custodial and legal risk. Freeze/blacklist capability likely (memory). Proof-of-reserves transparency has been criticized (memory). **No depeg incident found.** On Base: Morpho cbBTC collateral ≈ **$3.2B**, Aave v3 cbBTC supply ≈ **$248M**. |
| **WBTC** | Arbitrum `0x2f2a2543…5B0f` (canonical bridge). Base `0x0555E30d…2B9c` (LayerZero OFT). | 71.88 | **7,347.29** | BitGo, plus a **BiT Global (Justin Sun-linked) JV since Aug 2024**: 2-of-3 keys BitGo, 1-of-3 BiT Global. | Governance pushback (Sky/Maker offboarding proposals, Aave risk reviews). Coinbase delisted WBTC; BiT Global sued and later dropped the suit. On Base it carries LayerZero bridge-message risk. Aave Arbitrum WBTC supply ≈ $249M. |
| **tBTC** | Arbitrum `0x6c84a8f1…dE40`, Base `0x236aa509…794b` | 45.60 | 80.02 | Threshold Network threshold-signer custody (decentralized) | Thin L2 liquidity. A claimed blocked invalid-mint attempt on 2026-05-18 appears in a weak, unverified source. |
| **LBTC** | Base `0xecAc9C5F…11c1` | 133.63 | not at that address | Lombard (Babylon-staked BTC, consortium custody) | Yield-bearing but small on Base. Cross-chain messaging risk: the **Kelp rsETH cross-chain spoofing hack of 2026-04-18 ($293M, Ethereum and Arbitrum)** shows the bridged-LST failure mode. |

Market context (third-party snapshot, 2026-09-16): WBTC ≈ $7.5B, cbBTC close behind, LBTC ≈ $0.78B, tBTC ≈ $0.33B (https://eco.com/support/en/articles/15220202-tokenized-bitcoin-supply-2026-market-size-and-growth-trajectory).

**Recommendation:** hold the BTC leg as **cbBTC on Base**. It is the deepest pool, it trades at about 1–2 bps of cost for these sizes, and it is the asset the main lending markets use. Treat Coinbase custody and freeze risk as an accepted, documented risk. At $5k, consider a minority tBTC slice only if its Base liquidity improves.

Sources:
- https://bitgo.com/resources/blog/bitgo-to-move-wbtc-to-multi-jurisdictional-custody-to-accelerate-global/
- https://governance.aave.com/t/chaos-labs-wbtc-bitgo-custody-update/18607
- https://www.criptonoticias.com/tecnologia/sky-cancelaria-plan-eliminar-wbtc
- DefiLlama hacks API (Kelp)

---

## 5. Yield on BTC and stablecoins

Source: the live DefiLlama yields API on 2026-10-29: `https://yields.llama.fi/pools` (15,929 pools) and `https://yields.llama.fi/lendBorrow`.

**Caveat:** for lending pools, `tvlUsd` is **available liquidity (supply − borrow)**, not total deposits. I confirmed this against lendBorrow: Aave Base USDC tvl $16.3M = supply $189.8M − borrow $173.5M.

### 5.1 Stablecoins

| Chain | Venue | APY now | 30-day mean | Size | Notes |
|---|---|---|---|---|---|
| Base | Morpho vault Steakhouse/Grove USDC | 6.23% | 4.77% | $505M | Curated vault, instant withdraw subject to liquidity |
| Base | Morpho vault Spark USDC | 5.55% | 4.19% | $495M | |
| Base | Morpho vault "Sirloin" USDC (Steakhouse) | 6.83% | 5.82% | $473M | |
| Base | Morpho vault Gauntlet USDC Prime | 6.19% | 4.67% | $405M | |
| Base | **Aave v3 USDC** | 6.22% (5.05 base + 1.17 reward) | 5.07% | supply $190M / borrow $173M | **91% utilization**, so withdrawals can be delayed at peaks |
| Base | Fluid USDC | 4.41% | 7.81% | $7.5M liquidity | |
| Arbitrum | Fluid USDC | 3.73% | 5.37% | $64M liquidity | |
| Arbitrum | Aave v3 USDC | 2.44% | 2.76% | supply $218M / borrow $168M | 77% utilization |
| Arbitrum | Compound v3 USDC / USDT | 3.15% / 2.37% | | | |
| Arbitrum | Spark Savings USDS | 3.80% | 3.75% | $476M | |
| Arb / Base | Pendle PTs | e.g. PT-sUSDai Arbitrum ≈10% fixed to 2027-02-25 | | $5M | Exotic underlyings. Fixed maturity; early exit at market price. |
| Arb / Base | Euler v2 | – | | <$1M per vault | Negligible on these chains |

### 5.2 BTC

| Venue | APY |
|---|---|
| Aave v3 Base cbBTC supply | **0.01%** (borrow APY 0.65%) |
| Aave v3 Arbitrum WBTC | **0.02%** |
| Morpho cbBTC (Base) | 0%. It is collateral, not lent out. |
| Fluid, Compound, Euler cbBTC/WBTC | ≈0% |
| Dolomite WBTC (Arbitrum) | 0.95% |
| Concentrated-liquidity LPs (Uniswap v3 Base WETH-cbBTC 0.05% ≈ 33%, USDC-cbBTC ≈ 27%) | Fee APYs. Highly volatile, carry impermanent loss, need active range management. Not passive yield. |

**Implications for a BTC benchmark:**
- There is **no material passive BTC yield on L2 lending.** Any stablecoin allocation is a bet against BTC with a 4–6% coupon.
- Borrowing USDC against cbBTC costs about 6.1% on Aave Base, which is the same as the deposit rate, so a cbBTC-collateral loop has **no positive carry**.

### 5.3 Lock and withdrawal terms
- **Aave, Compound v3, Morpho vaults, Fluid:** no lock. Withdrawal depends on idle liquidity, so high utilization means possible delay. Fluid uses rate-limited withdrawal "expansion" limits (memory).
- **Morpho vaults** add **curator risk**. In the Stream Finance xUSD collapse (Nov 2025, about $285M of exposure across Euler, Morpho, Silo and Gearbox), fixed-price oracles on xUSD collateral created bad debt in some curated vaults. The MEV Capital Arbitrum USDC vault had $628k exposure, while Steakhouse reportedly had none (https://www.theblock.co/post/377491/analysts-map-285m-in-potential-exposure-across-defi-after-stream-finances-93m-loss, https://decrypt.co/347285).

### 5.4 Exploit history from the DefiLlama hacks DB

`https://api.llama.fi/hacks`: 1,328 entries, latest 2026-10-28, checked live.

| Protocol | Incidents |
|---|---|
| Aave | Periphery $56k (2024-08). **Aave V3 oracle misconfiguration $862k (2026-03-12, Ethereum).** |
| Morpho | LeadBlock Morpho Blue market oracle misconfiguration $250k (2024-10). |
| Fluid | **Fluid Lending private-key compromise $215k (2026-05-31, Ethereum).** |
| Euler | Euler V1 $197M (2023-03, donation attack; funds returned per public record). |
| Moonwell (Base) | $1.0M (2025-11), $1.78M (2026-02, oracle misconfiguration), **$8.7M (2026-08-27, spot-price manipulation)**. Avoid Moonwell markets and Moonwell-curated vaults unless re-reviewed. |
| Balancer V2 | $128M (2025-11-03, multi-chain including Arbitrum and Base). |
| Yearn | $9M (2025-11-30) |
| Compound v3, Pendle core | No core-protocol entries matched in this DB. Pendle's Penpie (a third party) was exploited in 2024 (memory). |

Audit status per protocol was not re-verified. Aave, Morpho Blue, Compound v3 and Pendle each have multiple public audits (memory). Use DefiLlama's `audits` / `audit_links` protocol fields (`https://api.llama.fi/protocol/{slug}`) to check programmatically.

---

## 6. Token and contract risk checks

| Tool | Live test (2026-10-29) | Use |
|---|---|---|
| **GoPlus Token Security** `api.gopluslabs.io/api/v1/token_security/{chainId}` | **Works without a key on Base.** For cbBTC it returned `is_open_source=1`, `is_proxy=1`, owner, `is_honeypot=0`, taxes 0, `trust_list=1`, `holder_count=514,194`. The approval-security v2 endpoint also responded. | Gate: reject any token that is not open source or is a honeypot, has non-zero tax, or has a hidden owner. Proxy tokens need an allowlist. Endpoints also cover malicious addresses, approval security, tx simulation, and phishing sites (https://docs.gopluslabs.io/reference/api-overview). Free-tier rate limits were not verified. |
| **honeypot.is** `api.honeypot.is/v2/IsHoneypot` | **Base: works** (simulated buy/sell, taxes, holder analysis). **Arbitrum (42161): `{"code":400,"error":"Invalid chain"}`.** | Second opinion, Base only. |
| **Etherscan API V2** | `api.etherscan.io/v2/chainlist`: **Arbitrum One "Free-tier available"; Base Mainnet and Base Sepolia "Paid Plan required"**. Source code and ABI endpoints are free on all chains. | Verified-source and ABI checks work on both chains for free. Tx/log queries on Base need a paid plan or an alternative. |
| **Blockscout** `base.blockscout.com/api/v2/...` | Returned a Cloudflare "Just a moment…" challenge to curl. | Programmatic use not verified. Blockscout offers a keyed PRO API (not tested). |
| **DefiLlama hacks** `api.llama.fi/hacks` | Works without a key. The `pro-api` variant needs a key. | Gate protocol allowlist changes on "no incident in last N days". |
| **DefiLlama yields / lendBorrow** | Works | APY, TVL, utilization and 30-day mean for allocation decisions. |
| De.Fi scanner | Not tested | Couldn't verify a public API. |
| **revoke.cash** | Repo active (MIT, last commit 2026-10-26) | Manual UI. For the agent, read `Approval` logs via `eth_getLogs` plus `allowance()` calls. |
| **Permit2** (`Uniswap/permit2`) | Immutable; last commit 2024-08-19 | Permit2 allowances are separate (`allowance(owner, token, spender)`) and must be checked and revoked there too. Use `lockdown` / `approve(…,0)`. |

**Approval hygiene policy:**
- Exact-amount approvals only, or a cap no larger than one trade's size.
- Spenders allowlisted per protocol (GPv2VaultRelayer, Aave Pool, Morpho vault).
- After each trade, assert the residual allowance is 0 or below the cap.
- Run a daily log scan for unexpected `Approval` events from the Safe.

Approval abuse is the most frequent 2025–26 hack technique in the DB: Aperture, ZetaChain, Ekubo, Limit Break, Gondi, Bitmor (Base).

---

## 7. Fork testing

- **Foundry:** `foundry-rs/foundry` v1.8.7, released 2026-10-29. Apache-2.0/MIT. Very active.
- Anvil flags (verified at https://getfoundry.sh/anvil/reference/):
  - `--fork-url` (multiple URLs round-robin with failover)
  - `--fork-block-number` (negative = latest − n)
  - `--fork-chain-id` (offline restart from cache)
  - `--no-storage-caching`
  - `--compute-units-per-second` (default 330) / `--no-rate-limit`
  - `--retries` (5), `--timeout` (45 s)
  - `--auto-impersonate`
  - `--fork-transaction-hash`, `--fork-state-by-number`
  - `-n/--network` with values `ethereum|base|optimism|tempo|monad`. There is **no** `--optimism` flag any more, and Arbitrum is not mentioned.
- **Arbitrum quirks (memory, verify):** Anvil does not emulate Arbitrum precompiles (`ArbSys` 0x64, `ArbGasInfo` 0x6C). Contracts that call `ArbSys.arbBlockNumber()` revert on a fork. Gas accounting differs, because there is no L1 data-fee component. For Base, L1 data fees are likewise not modelled exactly. Size the gas buffer from mainnet receipts.
- **Hardhat:** `NomicFoundation/hardhat` is very active (commit 2026-10-29). Usable, but Foundry/Anvil is the faster fit for a Python policy engine calling RPC.
- **RPC for forking (live tests):**
  - `https://mainnet.base.org` **served historical state** (`eth_getBalance` at block 16,777,216 succeeded). It is rate-limited, so fine for light pinned forks.
  - `https://arb1.arbitrum.io/rpc` gave **"missing trie node"** for an old block. It is not archive, so a pinned fork goes stale quickly at 250 ms blocks.
  - PublicNode (`*-rpc.publicnode.com`): "Archive requests require a personal token".
  - **Alchemy free tier:** 30M CU/month, 15 rps (300 CU/s), all mainnets and testnets including Arbitrum and Base. The page doesn't clearly confirm archive on Free (https://www.alchemy.com/pricing).
  - Infura, QuickNode, dRPC and Tenderly Virtual TestNets: not verified.
- **Recommended workflow:**
  1. Run `anvil --fork-url $ALCHEMY_BASE --fork-block-number <pinned> --auto-impersonate`.
  2. Deploy the Safe and Roles from scratch on the fork.
  3. Apply the DeFi Kit permissions.
  4. Fund the Safe by impersonating a USDC whale.
  5. Run the whole LLM → policy → signer loop.
  6. Run **negative tests**: the agent attempts `transfer` to an attacker, an order with `receiver != avatar`, an approval to an unknown spender, or exceeding the allowance. Each must revert in Roles.
  7. Pre-trade, the policy engine `eth_call`-simulates the exact signed tx on a fresh fork at `latest`.
- **Testnets:** Base Sepolia (Etherscan API is paid there) and Arbitrum Sepolia (free). Liquidity there is not economically meaningful, so use testnets only for signer, Safe and Roles plumbing and for CoW on Sepolia. Use forks for anything price-related.
- **Vendor alternative:** Wayfinder's "Gorlami" virtual-testnet fork service (requires their API key). Almanak's `--network anvil` paper-trading mode is a ready-made reference harness.

---

## 8. What I could not verify (open items)

1. The full CDP policy criteria list (calldata/param rules, cumulative USD limits). The policy-rules page returned 404, so only `ethValue` and `evmAddress` are confirmed. The CDP free tier shows 5,000 ops/month on current pages but 500 on an older one.
2. Privy pricing. Lit Vincent's current production status. Fireblocks pricing.
3. Zodiac Roles v2 "allowances" exact semantics (refill period, decimals) beyond the docs intro. Read https://docs.roles.gnosisguild.org (Allowances page) before relying on them.
4. Smart Sessions audit dates: the file names are ambiguous ("0826"). Whether Kernel v4 has been audited: the audit folder was removed in the v4 PR.
5. Base EIP-7702 activation date. I'm confident it is live (growthepie usage data) but did not see an official activation notice.
6. Uniswap Trading API response fields (gas USD, price impact) and the exact UniswapX minimum per chain. 1inch official pricing (third-party data only).
7. Gelato Web3 Functions EOL (competitor source only). ComposableCoW stop-loss handler addresses on Base and Arbitrum (third-party docs only).
8. cbBTC freeze/blacklist function and its proof-of-reserves status. LBTC on Arbitrum (not found at the Ethereum address). tBTC May 2026 mint-attempt claim.
9. GoPlus and honeypot.is free-tier rate limits. Blockscout programmatic access (blocked by a Cloudflare challenge). De.Fi API.
10. Whether Almanak's "managed gateway" contacts Almanak servers.
11. Hey Anon: no public SDK found.
12. When web3.py moved to ApeWorX, and any governance announcement for it.
13. Anvil handling of Arbitrum precompiles (memory-based caveat).
