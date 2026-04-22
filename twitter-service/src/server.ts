import express from 'express';
import { Rettiwt } from 'rettiwt-api';
import dotenv from 'dotenv';
import path from 'path';

// Load env from parent backend/.env
dotenv.config({ path: path.join(__dirname, '../../backend/.env') });

const app = express();
const PORT = parseInt(process.env.TWITTER_SERVICE_PORT || '3001');

// ============================================================
// Round-Robin Multi-Key Manager
// ============================================================
class KeyManager {
  private keys: string[] = [];
  private instances: Rettiwt[] = [];
  private currentIndex = 0;
  private failCounts: Map<number, number> = new Map();

  constructor() {
    // Load all TWITTER_API_KEY, TWITTER_API_KEY2, TWITTER_API_KEY3, etc.
    const envKeys = Object.keys(process.env)
      .filter(k => k.startsWith('TWITTER_API_KEY'))
      .sort((a, b) => {
        const getNum = (s: string) => {
          const m = s.match(/(\d+)$/);
          return m ? parseInt(m[1]) : 1;
        };
        return getNum(a) - getNum(b);
      });

    for (const keyName of envKeys) {
      const val = process.env[keyName];
      if (val && val.trim() && val !== 'your_twitter_api_key_here') {
        this.keys.push(val);
        this.instances.push(new Rettiwt({ apiKey: val }));
        this.failCounts.set(this.keys.length - 1, 0);
        console.log(`[Twitter] Loaded key from ${keyName}`);
      }
    }

    // Fallback to guest mode if no keys
    if (this.instances.length === 0) {
      this.instances.push(new Rettiwt());
      console.log('[Twitter] No API keys found - using Guest Auth');
    }

    console.log(`[Twitter] ${this.keys.length} API keys loaded for round-robin`);
  }

  get keyCount(): number {
    return this.keys.length;
  }

  /**
   * Get next Rettiwt instance (round-robin)
   */
  next(): Rettiwt {
    if (this.instances.length <= 1) return this.instances[0];
    this.currentIndex = (this.currentIndex + 1) % this.instances.length;
    return this.instances[this.currentIndex];
  }

  /**
   * Execute operation with automatic key rotation on failure
   */
  async execute<T>(operation: (client: Rettiwt) => Promise<T>, context: string): Promise<T> {
    const maxAttempts = Math.max(this.instances.length, 1) + 1;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const client = this.next();
      const keyIdx = this.currentIndex;

      try {
        const result = await operation(client);
        // Reset fail count on success
        this.failCounts.set(keyIdx, 0);
        return result;
      } catch (error: any) {
        const msg = error.message || String(error);
        const isRetryable = ['429', '401', '403', '500', '502', '503'].some(code => msg.includes(code));

        console.warn(`[Twitter] Key #${keyIdx + 1} failed (${attempt}/${maxAttempts}): ${msg}`);
        this.failCounts.set(keyIdx, (this.failCounts.get(keyIdx) || 0) + 1);

        if (!isRetryable || attempt === maxAttempts) {
          throw error;
        }

        // Small delay before retry with next key
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }

    throw new Error(`All ${maxAttempts} attempts failed for: ${context}`);
  }
}

const keyManager = new KeyManager();

// ============================================================
// API Endpoints
// ============================================================

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    keys_loaded: keyManager.keyCount,
    mode: keyManager.keyCount > 0 ? 'authenticated' : 'guest',
  });
});

/**
 * Search tweets by keyword (for token sentiment analysis)
 * GET /search?q=KITE&count=30
 */
app.get('/search', async (req, res) => {
  const query = (req.query.q as string) || 'KITE';
  const count = Math.min(parseInt(req.query.count as string) || 20, 50);

  try {
    console.log(`[Twitter] Searching: "${query}" (count: ${count})`);

    const response = await keyManager.execute(
      (client) => client.tweet.search({ includeWords: [query] }, count),
      `search("${query}")`
    );

    if (!response || !response.list || response.list.length === 0) {
      return res.json({ tweets: [], total: 0, query, source: 'rettiwt' });
    }

    const tweets = response.list.map((tweet: any) => ({
      id: tweet.id,
      text: tweet.fullText || '',
      username: tweet.tweetBy?.userName || 'unknown',
      display_name: tweet.tweetBy?.fullName || '',
      timestamp: tweet.createdAt,
      likes: tweet.likeCount || 0,
      retweets: tweet.retweetCount || 0,
      replies: tweet.replyCount || 0,
      quotes: tweet.quoteCount || 0,
      views: tweet.viewCount || 0,
      bookmarks: tweet.bookmarkCount || 0,
      is_reply: !!tweet.replyTo,
      is_retweet: !!tweet.retweetedTweet,
      is_quote: !!tweet.quoted,
      source: 'rettiwt',
    }));

    console.log(`[Twitter] Found ${tweets.length} REAL tweets for "${query}"`);
    res.json({ tweets, total: tweets.length, query, source: 'rettiwt' });
  } catch (error: any) {
    console.error(`[Twitter] Search failed after all retries: ${error.message}`);
    res.json({ tweets: [], total: 0, query, source: 'rettiwt', error: error.message });
  }
});

/**
 * Get tweets from specific crypto influencers / KOLs
 * GET /influencers?token=KITE&count=10
 */
app.get('/influencers', async (req, res) => {
  const token = (req.query.token as string) || 'KITE';
  const count = Math.min(parseInt(req.query.count as string) || 10, 20);

  const cryptoAccounts = [
    'CryptoGodJohn', 'inversebrah', 'AltcoinGordon',
    'crypto_birb', 'TheCryptoLark', 'CryptoCred',
    'coaborin', 'BluntzCapital', 'CryptoKaleo',
  ];

  try {
    const response = await keyManager.execute(
      (client) => client.tweet.search(
        { fromUsers: cryptoAccounts, includeWords: [token] },
        count
      ),
      `influencers("${token}")`
    );

    const tweets = (response?.list || []).map((tweet: any) => ({
      id: tweet.id,
      text: tweet.fullText || '',
      username: tweet.tweetBy?.userName || 'unknown',
      timestamp: tweet.createdAt,
      likes: tweet.likeCount || 0,
      retweets: tweet.retweetCount || 0,
      views: tweet.viewCount || 0,
      source: 'rettiwt_influencer',
    }));

    res.json({ tweets, total: tweets.length, token, source: 'rettiwt_influencer' });
  } catch (error: any) {
    res.json({ tweets: [], total: 0, token, error: error.message });
  }
});

/**
 * Get a specific user's timeline
 * GET /user/:username?count=10
 */
app.get('/user/:username', async (req, res) => {
  const { username } = req.params;
  const count = Math.min(parseInt(req.query.count as string) || 10, 20);

  try {
    const userDetails = await keyManager.execute(
      (client) => client.user.details(username),
      `user("${username}")`
    );

    if (!userDetails) {
      return res.json({ error: 'User not found', username });
    }

    const timeline = await keyManager.execute(
      (client) => client.user.timeline(userDetails.id, count),
      `timeline("${username}")`
    );

    const tweets = (timeline?.list || []).map((tweet: any) => ({
      id: tweet.id,
      text: tweet.fullText || '',
      username: tweet.tweetBy?.userName || 'unknown',
      timestamp: tweet.createdAt,
      likes: tweet.likeCount || 0,
      retweets: tweet.retweetCount || 0,
      views: tweet.viewCount || 0,
      source: 'rettiwt_timeline',
    }));

    res.json({
      user: {
        id: userDetails.id,
        username: userDetails.userName,
        name: userDetails.fullName,
        followers: userDetails.followersCount,
        following: userDetails.followingsCount,
      },
      tweets,
      total: tweets.length,
    });
  } catch (error: any) {
    res.json({ error: error.message, username });
  }
});

app.listen(PORT, () => {
  console.log(`[Twitter Service] Running on http://localhost:${PORT}`);
  console.log(`[Twitter Service] Keys: ${keyManager.keyCount} (round-robin)`);
  console.log(`[Twitter Service] Endpoints:`);
  console.log(`  Search:      GET /search?q=KITE&count=20`);
  console.log(`  Influencers: GET /influencers?token=KITE`);
  console.log(`  User:        GET /user/elonmusk?count=5`);
  console.log(`  Health:      GET /health`);
});
