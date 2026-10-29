# Extending the agent

Rule of thumb: **new capability = human work + frozen-layer review**. The agent itself may only tune bounded
parameters and its playbook (SELF_IMPROVEMENT.md D6).

## A new strategy
1. Write the rule as a pure function in `btcagent/strategies/rules.py` (features in → target weights + stops +
   rule states out; point-in-time only). Add its params to `evolvable/strategies.yaml` and bounds to
   `frozen/param_bounds.yaml`.
2. Pre-register variants in a new `scripts/research_*.py` **before** looking at results; record the date in
   STRATEGY.md. Count every variant as a trial (deflated Sharpe).
3. It must beat the champion in the gatekeeper's terms (full history, ≤1 worse cycle, all stress windows,
   bootstrap p ≤ 0.2), then run in shadow (add it as a `Book` in `ImprovementLoop.setup_shadows`) for ≥ 8 weeks.
4. Re-lock the frozen layer; promote by editing `evolvable/strategies.yaml` (a git commit) or via a forced proposal
   (`btcagent review`).

## A new protocol (e.g. a Morpho USDC vault)
1. `btcagent risk-check <token or vault address>`; read audits; check DefiLlama hacks and L2Beat.
2. Add the contract with only the selectors you need to `frozen/allowlists.yaml` (`contracts`, and the spender under
   `token_approvals.spenders`), a protocol entry with `max_weight`, then re-lock.
3. Implement `lend()` for it in `execution/evm.py` (approve exact → call → revoke), extend
   `signer/policy.py` with a decoder that checks `onBehalfOf`/`receiver` == our wallet, and add fork tests.

## A new chain
Add it under `chains`, `tokens`, `contracts` in the allowlists; point an `EvmExecutor` at its RPC; add a fork test
(Anvil supports any EVM chain). Bridging is deliberately not supported (bridge risk; research B).

## A new venue (CEX)
Add `venues.<id>` with its `ccxt_id`, `cex_pairs`, fees in `execution/market.py::VENUE_FEES_BPS`, keys in the
signer's environment (trade-only), and test against its demo/testnet first (`BTCAGENT_<VENUE>_DEMO=1`).

## A new model or provider
`config/models.yaml` only: add a provider (`kind: openai` for any OpenAI-compatible API) and reference it from a
role. Run `scripts/smoke_llm.py <provider:model>` and the live-LLM test suite. Treat it as a challenger.

## Safe + Zodiac Roles (recommended before the 5k stage)
Deploy a Safe owned by a hardware wallet; grant the agent's key a Zodiac Roles v2 role scoped with the karpatkey
DeFi Kit presets (Uniswap swaps with recipient = Safe, Aave supply/withdraw), with allowances per period. The off-
chain signer policy stays as the first layer; the Roles modifier becomes an on-chain second layer, and the hardware
owner can revoke the role in one transaction (kill switch independent of the rig).
