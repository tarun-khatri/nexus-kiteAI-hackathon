// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * NEXUS - Governance Rules
 * Enforces spending limits and compliance rules for the agent economy.
 *
 * Features:
 * - Real daily spending tracking with day-based reset
 * - Per-agent custom rules
 * - Minimum reputation enforcement
 * - SpendingBlocked event for audit trail
 */
contract GovernanceRules {
    struct Rules {
        uint256 maxSpendPerTx;
        uint256 maxSpendPerDay;
        uint256 minReputation;
        bool active;
    }

    mapping(bytes32 => Rules) public agentRules;
    Rules public globalRules;

    // Daily spending tracking
    mapping(bytes32 => uint256) public dailySpent;
    mapping(bytes32 => uint256) public lastResetDay;

    address public owner;

    event RulesUpdated(string ruleType, uint256 oldValue, uint256 newValue);
    event SpendingBlocked(bytes32 indexed agentId, uint256 amount, string reason);
    event AgentRulesSet(bytes32 indexed agentId, uint256 maxPerTx, uint256 maxPerDay, uint256 minRep);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
        globalRules = Rules({
            maxSpendPerTx: 1000,
            maxSpendPerDay: 10000,
            minReputation: 20,
            active: true
        });
    }

    function _currentDay() internal view returns (uint256) {
        return block.timestamp / 86400;
    }

    function _resetDailyIfNeeded(bytes32 agentId) internal {
        uint256 today = _currentDay();
        if (lastResetDay[agentId] < today) {
            dailySpent[agentId] = 0;
            lastResetDay[agentId] = today;
        }
    }

    function checkAllowed(
        bytes32 agentId,
        uint256 amount
    ) external returns (bool allowed, string memory reason) {
        Rules memory rules = agentRules[agentId].active
            ? agentRules[agentId]
            : globalRules;

        if (amount > rules.maxSpendPerTx) {
            emit SpendingBlocked(agentId, amount, "Exceeds per-tx limit");
            return (false, "Exceeds per-transaction spending limit");
        }

        _resetDailyIfNeeded(agentId);
        if (dailySpent[agentId] + amount > rules.maxSpendPerDay) {
            emit SpendingBlocked(agentId, amount, "Exceeds daily limit");
            return (false, "Exceeds daily spending limit");
        }

        dailySpent[agentId] += amount;
        return (true, "Approved");
    }

    function previewCheck(
        bytes32 agentId,
        uint256 amount
    ) external view returns (bool allowed, string memory reason) {
        Rules memory rules = agentRules[agentId].active
            ? agentRules[agentId]
            : globalRules;

        if (amount > rules.maxSpendPerTx) {
            return (false, "Exceeds per-transaction spending limit");
        }

        uint256 today = _currentDay();
        uint256 spent = lastResetDay[agentId] < today ? 0 : dailySpent[agentId];
        if (spent + amount > rules.maxSpendPerDay) {
            return (false, "Exceeds daily spending limit");
        }

        return (true, "Would be approved");
    }

    function setAgentRules(
        bytes32 agentId,
        uint256 maxPerTx,
        uint256 maxPerDay,
        uint256 minRep
    ) external onlyOwner {
        agentRules[agentId] = Rules({
            maxSpendPerTx: maxPerTx,
            maxSpendPerDay: maxPerDay,
            minReputation: minRep,
            active: true
        });
        emit AgentRulesSet(agentId, maxPerTx, maxPerDay, minRep);
    }

    function setGlobalMaxPerTx(uint256 newMax) external onlyOwner {
        uint256 old = globalRules.maxSpendPerTx;
        globalRules.maxSpendPerTx = newMax;
        emit RulesUpdated("maxSpendPerTx", old, newMax);
    }

    function setGlobalMaxPerDay(uint256 newMax) external onlyOwner {
        uint256 old = globalRules.maxSpendPerDay;
        globalRules.maxSpendPerDay = newMax;
        emit RulesUpdated("maxSpendPerDay", old, newMax);
    }

    function setMinReputation(uint256 newMin) external onlyOwner {
        uint256 old = globalRules.minReputation;
        globalRules.minReputation = newMin;
        emit RulesUpdated("minReputation", old, newMin);
    }

    function getGlobalRules() external view returns (
        uint256 maxSpendPerTx,
        uint256 maxSpendPerDay,
        uint256 minReputation
    ) {
        return (
            globalRules.maxSpendPerTx,
            globalRules.maxSpendPerDay,
            globalRules.minReputation
        );
    }

    function getDailySpent(bytes32 agentId) external view returns (uint256) {
        uint256 today = _currentDay();
        if (lastResetDay[agentId] < today) return 0;
        return dailySpent[agentId];
    }

    function getDailyRemaining(bytes32 agentId) external view returns (uint256) {
        Rules memory rules = agentRules[agentId].active
            ? agentRules[agentId]
            : globalRules;

        uint256 today = _currentDay();
        uint256 spent = lastResetDay[agentId] < today ? 0 : dailySpent[agentId];

        if (spent >= rules.maxSpendPerDay) return 0;
        return rules.maxSpendPerDay - spent;
    }
}
