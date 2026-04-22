/**
 * NEXUS - Smart Contract Deployment Script
 * Deploys all 4 contracts to Kite Aero Testnet (FREE)
 *
 * Usage:
 *   npx hardhat run deploy/deploy.js --network kiteTestnet
 *   npx hardhat run deploy/deploy.js --network hardhat  (local test)
 */

const hre = require("hardhat");

async function main() {
  console.log("=".repeat(50));
  console.log("  NEXUS - Deploying Smart Contracts");
  console.log("=".repeat(50));

  const [deployer] = await hre.ethers.getSigners();
  console.log(`\nDeployer: ${deployer.address}`);

  // 1. Deploy AgentRegistry
  console.log("\n[1/4] Deploying AgentRegistry...");
  const AgentRegistry = await hre.ethers.getContractFactory("AgentRegistry");
  const registry = await AgentRegistry.deploy();
  await registry.waitForDeployment();
  const registryAddr = await registry.getAddress();
  console.log(`  AgentRegistry: ${registryAddr}`);

  // 2. Deploy ReputationTracker
  console.log("[2/4] Deploying ReputationTracker...");
  const ReputationTracker = await hre.ethers.getContractFactory("ReputationTracker");
  const reputation = await ReputationTracker.deploy();
  await reputation.waitForDeployment();
  const reputationAddr = await reputation.getAddress();
  console.log(`  ReputationTracker: ${reputationAddr}`);

  // 3. Deploy PaymentRouter
  console.log("[3/4] Deploying PaymentRouter...");
  const PaymentRouter = await hre.ethers.getContractFactory("PaymentRouter");
  const payments = await PaymentRouter.deploy();
  await payments.waitForDeployment();
  const paymentsAddr = await payments.getAddress();
  console.log(`  PaymentRouter: ${paymentsAddr}`);

  // 4. Deploy GovernanceRules
  console.log("[4/4] Deploying GovernanceRules...");
  const GovernanceRules = await hre.ethers.getContractFactory("GovernanceRules");
  const governance = await GovernanceRules.deploy();
  await governance.waitForDeployment();
  const governanceAddr = await governance.getAddress();
  console.log(`  GovernanceRules: ${governanceAddr}`);

  console.log("\n" + "=".repeat(50));
  console.log("  All contracts deployed successfully!");
  console.log("=".repeat(50));
  console.log(`
Add these to your .env file:
AGENT_REGISTRY_ADDRESS=${registryAddr}
REPUTATION_TRACKER_ADDRESS=${reputationAddr}
PAYMENT_ROUTER_ADDRESS=${paymentsAddr}
GOVERNANCE_RULES_ADDRESS=${governanceAddr}
  `);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
