// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * NEXUS - Agent Registry (Open Marketplace)
 * The decentralized "phone book" of the agent economy.
 *
 * Features:
 * - Open registration: any wallet can register agents
 * - Capability-based discovery
 * - Agent status management (active/inactive)
 * - On-chain pricing
 * - Marketplace listing for agent discovery
 */
contract AgentRegistry {
    struct Agent {
        address walletAddress;
        string name;
        string description;
        string[] capabilities;
        uint256 pricePerQuery;
        uint256 reputationScore;
        bool active;
        uint256 registeredAt;
        uint256 jobsCompleted;
    }

    mapping(bytes32 => Agent) public agents;
    bytes32[] public agentList;
    mapping(address => bytes32[]) public agentsByOwner;

    address public owner;

    event AgentRegistered(bytes32 indexed passportId, string name, address wallet);
    event AgentUpdated(bytes32 indexed passportId, string field);
    event AgentDeactivated(bytes32 indexed passportId);
    event AgentReactivated(bytes32 indexed passportId);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * Register a new agent - OPEN to any wallet.
     * Anyone can register themselves as a service provider.
     */
    function registerAgent(
        bytes32 passportId,
        string memory name,
        string memory description,
        string[] memory capabilities,
        uint256 pricePerQuery
    ) external {
        require(!agents[passportId].active, "Agent already registered");
        require(bytes(name).length > 0, "Name required");

        agents[passportId] = Agent({
            walletAddress: msg.sender,
            name: name,
            description: description,
            capabilities: capabilities,
            pricePerQuery: pricePerQuery,
            reputationScore: 50,
            active: true,
            registeredAt: block.timestamp,
            jobsCompleted: 0
        });

        agentList.push(passportId);
        agentsByOwner[msg.sender].push(passportId);

        emit AgentRegistered(passportId, name, msg.sender);
    }

    /**
     * Get agent details
     */
    function getAgent(bytes32 passportId) external view returns (
        address walletAddress,
        string memory name,
        uint256 pricePerQuery,
        uint256 reputationScore,
        bool active,
        uint256 jobsCompleted
    ) {
        Agent storage a = agents[passportId];
        return (a.walletAddress, a.name, a.pricePerQuery, a.reputationScore, a.active, a.jobsCompleted);
    }

    /**
     * Get full agent details including description and capabilities
     */
    function getAgentFull(bytes32 passportId) external view returns (
        address walletAddress,
        string memory name,
        string memory description,
        uint256 pricePerQuery,
        uint256 reputationScore,
        bool active,
        uint256 jobsCompleted,
        uint256 registeredAt
    ) {
        Agent storage a = agents[passportId];
        return (a.walletAddress, a.name, a.description, a.pricePerQuery,
                a.reputationScore, a.active, a.jobsCompleted, a.registeredAt);
    }

    /**
     * Get total number of registered agents
     */
    function getAgentCount() external view returns (uint256) {
        return agentList.length;
    }

    /**
     * Get agent passport ID by index (for enumeration)
     */
    function getAgentAt(uint256 index) external view returns (bytes32) {
        require(index < agentList.length, "Index out of bounds");
        return agentList[index];
    }

    /**
     * Update agent's price (only agent owner)
     */
    function updatePrice(bytes32 passportId, uint256 newPrice) external {
        require(agents[passportId].walletAddress == msg.sender, "Not agent owner");
        agents[passportId].pricePerQuery = newPrice;
        emit AgentUpdated(passportId, "price");
    }

    /**
     * Update agent's description (only agent owner)
     */
    function updateDescription(bytes32 passportId, string memory newDesc) external {
        require(agents[passportId].walletAddress == msg.sender, "Not agent owner");
        agents[passportId].description = newDesc;
        emit AgentUpdated(passportId, "description");
    }

    /**
     * Increment job counter (owner or authorized operator)
     */
    function incrementJobs(bytes32 passportId) external onlyOwner {
        agents[passportId].jobsCompleted += 1;
    }

    /**
     * Deactivate an agent (agent owner or contract owner)
     */
    function deactivate(bytes32 passportId) external {
        require(
            agents[passportId].walletAddress == msg.sender || msg.sender == owner,
            "Not authorized"
        );
        agents[passportId].active = false;
        emit AgentDeactivated(passportId);
    }

    /**
     * Reactivate an agent (agent owner only)
     */
    function reactivate(bytes32 passportId) external {
        require(agents[passportId].walletAddress == msg.sender, "Not agent owner");
        agents[passportId].active = true;
        emit AgentReactivated(passportId);
    }

    /**
     * Get all agents owned by an address
     */
    function getAgentsByOwner(address ownerAddr) external view returns (bytes32[] memory) {
        return agentsByOwner[ownerAddr];
    }
}
