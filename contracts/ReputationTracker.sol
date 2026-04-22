// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * NEXUS - Reputation Tracker
 * Tracks how reliable each agent is.
 * Good agents get higher scores, bad agents get lower scores.
 * Scores are used by other agents when deciding who to hire.
 */
contract ReputationTracker {
    struct ReputationRecord {
        uint256 score;       // 0-100
        uint256 totalJobs;
        uint256 successfulJobs;
        uint256 failedJobs;
        uint256 lastUpdated;
    }

    mapping(bytes32 => ReputationRecord) public records; // passportId => record
    address public owner;

    event ReputationUpdated(bytes32 indexed passportId, uint256 oldScore, uint256 newScore, string reason);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function initializeAgent(bytes32 passportId) external onlyOwner {
        records[passportId] = ReputationRecord({
            score: 50,
            totalJobs: 0,
            successfulJobs: 0,
            failedJobs: 0,
            lastUpdated: block.timestamp
        });
    }

    function recordSuccess(bytes32 passportId, uint256 qualityScore) external onlyOwner {
        ReputationRecord storage r = records[passportId];
        uint256 oldScore = r.score;

        r.totalJobs++;
        r.successfulJobs++;

        // Reputation boost based on quality
        if (qualityScore >= 90) {
            r.score = _clamp(r.score + 2);
        } else if (qualityScore >= 70) {
            r.score = _clamp(r.score + 1);
        }

        r.lastUpdated = block.timestamp;
        emit ReputationUpdated(passportId, oldScore, r.score, "job_success");
    }

    function recordFailure(bytes32 passportId) external onlyOwner {
        ReputationRecord storage r = records[passportId];
        uint256 oldScore = r.score;

        r.totalJobs++;
        r.failedJobs++;
        r.score = r.score >= 5 ? r.score - 5 : 0;
        r.lastUpdated = block.timestamp;

        emit ReputationUpdated(passportId, oldScore, r.score, "job_failure");
    }

    function getReputation(bytes32 passportId) external view returns (uint256) {
        return records[passportId].score;
    }

    function getFullRecord(bytes32 passportId) external view returns (
        uint256 score,
        uint256 totalJobs,
        uint256 successfulJobs,
        uint256 failedJobs
    ) {
        ReputationRecord storage r = records[passportId];
        return (r.score, r.totalJobs, r.successfulJobs, r.failedJobs);
    }

    function _clamp(uint256 value) internal pure returns (uint256) {
        return value > 100 ? 100 : value;
    }
}
