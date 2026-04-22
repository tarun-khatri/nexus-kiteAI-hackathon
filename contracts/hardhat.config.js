require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: "../backend/.env" });

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  paths: {
    sources: ".",           // Contracts are in the root of contracts/
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
  networks: {
    // Kite Aero Testnet (FREE)
    kiteTestnet: {
      url: process.env.KITE_RPC_URL || "https://rpc-testnet.gokite.ai/",
      chainId: parseInt(process.env.KITE_CHAIN_ID || "2368"),
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
    },
    // Local hardhat for testing
    hardhat: {
      chainId: 31337,
    },
  },
};
