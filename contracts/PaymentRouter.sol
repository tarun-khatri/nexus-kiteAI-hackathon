// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * NEXUS - Payment Router
 * Handles all x402 micropayments between agents.
 *
 * Key features:
 * - Authorized operators can execute payments (not just owner)
 * - Agents can self-fund their accounts
 * - Mandate-aware: payments reference mandate IDs for audit
 * - Event-rich for off-chain indexing
 */
contract PaymentRouter {
    struct PaymentRecord {
        bytes32 fromAgent;
        bytes32 toAgent;
        uint256 amount;
        string purpose;
        bytes32 mandateId;
        uint256 timestamp;
    }

    PaymentRecord[] public payments;
    mapping(bytes32 => uint256) public balances;
    mapping(bytes32 => uint256) public totalEarned;
    mapping(bytes32 => uint256) public totalSpent;
    mapping(address => bool) public authorizedOperators;
    address public owner;

    event PaymentSent(
        bytes32 indexed fromAgent,
        bytes32 indexed toAgent,
        uint256 amount,
        string purpose,
        bytes32 mandateId,
        uint256 timestamp
    );

    event AgentFunded(bytes32 indexed passportId, uint256 amount, address funder);
    event OperatorAuthorized(address indexed operator, bool authorized);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyAuthorized() {
        require(
            msg.sender == owner || authorizedOperators[msg.sender],
            "Not authorized"
        );
        _;
    }

    constructor() {
        owner = msg.sender;
        authorizedOperators[msg.sender] = true;
    }

    /**
     * Authorize an address to execute payments (e.g., an AA wallet or backend)
     */
    function authorizeOperator(address operator, bool authorized) external onlyOwner {
        authorizedOperators[operator] = authorized;
        emit OperatorAuthorized(operator, authorized);
    }

    /**
     * Fund an agent's balance. Can be called by anyone (self-funding supported).
     */
    function fundAgent(bytes32 passportId, uint256 amount) external {
        balances[passportId] += amount;
        emit AgentFunded(passportId, amount, msg.sender);
    }

    /**
     * Execute a payment between two agents.
     * Can be called by owner OR any authorized operator.
     * Includes mandateId for audit trail linkage.
     */
    function payForService(
        bytes32 fromAgent,
        bytes32 toAgent,
        uint256 amount,
        string memory purpose
    ) external onlyAuthorized {
        require(balances[fromAgent] >= amount, "Insufficient balance");
        require(amount > 0, "Amount must be positive");

        balances[fromAgent] -= amount;
        balances[toAgent] += amount;
        totalSpent[fromAgent] += amount;
        totalEarned[toAgent] += amount;

        bytes32 mandateId = bytes32(0);

        payments.push(PaymentRecord({
            fromAgent: fromAgent,
            toAgent: toAgent,
            amount: amount,
            purpose: purpose,
            mandateId: mandateId,
            timestamp: block.timestamp
        }));

        emit PaymentSent(fromAgent, toAgent, amount, purpose, mandateId, block.timestamp);
    }

    /**
     * Execute payment with explicit mandate reference (for audit trail)
     */
    function payForServiceWithMandate(
        bytes32 fromAgent,
        bytes32 toAgent,
        uint256 amount,
        string memory purpose,
        bytes32 mandateId
    ) external onlyAuthorized {
        require(balances[fromAgent] >= amount, "Insufficient balance");
        require(amount > 0, "Amount must be positive");

        balances[fromAgent] -= amount;
        balances[toAgent] += amount;
        totalSpent[fromAgent] += amount;
        totalEarned[toAgent] += amount;

        payments.push(PaymentRecord({
            fromAgent: fromAgent,
            toAgent: toAgent,
            amount: amount,
            purpose: purpose,
            mandateId: mandateId,
            timestamp: block.timestamp
        }));

        emit PaymentSent(fromAgent, toAgent, amount, purpose, mandateId, block.timestamp);
    }

    function getBalance(bytes32 passportId) external view returns (uint256) {
        return balances[passportId];
    }

    function getPaymentCount() external view returns (uint256) {
        return payments.length;
    }

    function getTotalEarned(bytes32 passportId) external view returns (uint256) {
        return totalEarned[passportId];
    }

    function getTotalSpent(bytes32 passportId) external view returns (uint256) {
        return totalSpent[passportId];
    }

    function isOperator(address addr) external view returns (bool) {
        return authorizedOperators[addr];
    }
}
