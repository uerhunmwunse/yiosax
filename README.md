Price Tracker Telegram Bot - README

Summary:
This is a Telegram bot that helps users track product prices from actual online stores using APIs.
The bot collects product details from the user through a guided interaction (e.g., category, model, price)
and checks for real-time product data using the Rainforest API. It aims to help users monitor and receive alerts
about product availability and pricing without browsing multiple store websites.

⚙️ Tech Stack
-------------
- Language: Python
- Platform: Telegram Bot API
- APIs Used: Rainforest API (currently the only integrated API)
- Database: SQLite (via Python)
- Helpers: print debugging, AI assistance (e.g., tracing bugs, logic refactoring)
- Logging: Basic logging implemented for error tracking(AI assistance)

 Imports & Environment
------------------------
The project requires several imports and API keys set via environment variables. These include:

- Python Packages (install with pip):
  anyio==4.9.0
  certifi==2025.6.15
  charset-normalizer==3.4.2
  fuzzywuzzy==0.18.0
  h11==0.16.0
  httpcore==1.0.9
  httpx==0.28.1
  idna==3.10
  levenshtein==0.27.1
  python-dotenv==1.1.1
  python-levenshtein==0.27.1
  python-telegram-bot==22.2
  rapidfuzz==3.13.0
  requests==2.32.3
  sniffio==1.3.1
  typing-extensions==4.14.0
  urllib3==2.5.0

Install all required packages with:
> pip install anyio certifi fuzzywuzzy python-levenshtein python-dotenv python-telegram-bot rapidfuzz requests

- API Access Required:
  • Telegram Bot API Key (set as TELEGRAM_TOKEN)
  • Rainforest API Key (set as RAINFOREST_API_KEY)

Create a .env file with these values:
TELEGRAM_TOKEN=your_telegram_token_here
RAINFOREST_API_KEY=your_rainforest_api_key_here

How to Use
-------------
1. Start the bot on Telegram with /start
2. Follow the guided prompts to select:
   - Product category
   - Brand/manufacturer
   - Model details
   - Target price
3. Confirm product match when shown
4. Receive periodic price alerts
5. Use /stop Product_Name to cancel tracking

Development Journey & Technical Notes
----------------------------------------

1. Early API Attempts & Rethinking the Flow

Started with scraping but dropped it - results were unstable and unrelated. Moved to APIs:
• Best Buy: Limited access, returned random accessories
• Sein: Poor docs, no structure, missing categories
• Dummy APIs: Sandbox data only, wasted time

Shifted to guided interaction:
Category → Manufacturer → Model → Storage → Price

2. Data Type Nightmares

Hit several roadblocks from type mismatches:
• Tried comparing prices without checking if API returned string/dict/float
• Overwriting product names during confirmation flow led to "ghost products"
• Database stored different format than what notification system expected

Fixed by:
• Adding type checks before comparisons:
  if isinstance(price, dict): real_price = price.get('value')
• Using consistent naming throughout flow
• Print-debugging every step to catch mismatches

3. Matching Algorithm Tuning

Initial matching missed valid products:
• Too strict: "iPhone 14 Pro" wouldn't match "Apple iPhone 14 Pro Max 256GB"
• Too loose: "PlayStation 5" matched PS5 controller skins

Solved with:
• Fuzzy matching (thanks to AI suggestions)
• Keyword priority system
• Category-specific matching rules
• Normalization: str.lower() + special character removal

4. Switching to Rainforest API

Finally landed on Rainforest API:
• Supports natural product searches
• Returns Amazon-style structured data
• Still needed manual filtering (e.g., laptop searches returning sleeves)

Added helper filters: is_real_laptop_product(), is_real_console(), etc.

5. Database Growing Pains

As a database newbie, faced multiple issues:
• Created tables with wrong column counts
• Changed key names mid-development ("model" → "model_name")
• Tried accessing data like dicts when it was JSON strings
• Missed type conversions when retrieving prices

Fixed through:
• SQL error message analysis (with AI help)
• Consistent naming conventions
• JSON serialization/deserialization
• Simple try/except wrappers

Future Plans
---------------
- Integrate Best Buy/Walmart APIs for wider coverage
- Smart accessory filtering
- User tier system (free vs premium)
- OpenAI for natural language queries ("Find me iPhone under $500")
- One-click re-tracking

Conclusion

This entire process has been a journey of iteration and self-learning. I started with no scraping experience, no API integration experience, and no database knowledge — just the goal of building a working Telegram bot.

Every fix created new challenges: poor API documentation, broken user flows, mismatched data, vague product results, or database errors. But I improved by constantly debugging, refining logic, and adapting — and by using AI tools as a support system.

Now, with the Rainforest API, keyword filters, step-by-step product queries, and a simple working database, the bot runs more reliably and offers a smoother experience to users.

I’m still building on a foundation of basic knowledge, but this project has taught me a lot — not by theory, but by trial, error, and real-world problem-solving.

Key takeaways:
1. Always check data types before operations
2. Naming consistency saves hours of debugging
3. Print statements are lifelines
4. Fuzzy matching beats exact matching for real-world products
5. Databases seem simple until they're not
