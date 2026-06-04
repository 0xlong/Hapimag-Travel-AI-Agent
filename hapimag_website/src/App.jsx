import { useMemo, useState } from "react";
import { Bot, ChevronDown, CloudRain, CloudSun, Cloud, Sun, Snowflake, CloudFog, CloudLightning, Droplets, Search, SlidersHorizontal, Thermometer, X } from "lucide-react";
import { destinations, filterTags } from "./data/destinations.js";

const countries = ["All Destinations", ...new Set(destinations.map((item) => item.country))];

function App() {
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("All Destinations");
  const [selectedTags, setSelectedTags] = useState([]);
  const [isDestinationOpen, setIsDestinationOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [naturalPrompt, setNaturalPrompt] = useState("");
  const [aiResults, setAiResults] = useState(null);
  const [aiAlternativeResults, setAiAlternativeResults] = useState([]);
  const [aiRecommendationText, setAiRecommendationText] = useState("");
  const [aiCriteria, setAiCriteria] = useState(null);
  const [aiError, setAiError] = useState("");
  const [isAiSearching, setIsAiSearching] = useState(false);
  const [weatherForecasts, setWeatherForecasts] = useState({});

  const filteredDestinations = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return destinations.filter((destination) => {
      const text = [
        destination.name,
        destination.location,
        destination.country,
        destination.description,
        destination.tags.join(" "),
      ]
        .join(" ")
        .toLowerCase();

      const matchesQuery = !normalizedQuery || text.includes(normalizedQuery);
      const matchesCountry = country === "All Destinations" || destination.country === country;
      const matchesTags =
        selectedTags.length === 0 ||
        selectedTags.every((tag) => destination.tags.includes(tag));

      return matchesQuery && matchesCountry && matchesTags;
    });
  }, [country, query, selectedTags]);

  const toggleTag = (tag) => {
    setSelectedTags((current) =>
      current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag]
    );
  };

  const handleNaturalSearch = async (event) => {
    event.preventDefault();

    const prompt = naturalPrompt.trim();
    if (!prompt) {
      return;
    }

    setIsAiSearching(true);
    setAiError("");

    try {
      const response = await fetch("http://localhost:8000/api/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: prompt }),
      });

      if (!response.ok) {
        throw new Error("Search service did not respond.");
      }

      const data = await response.json();
      setAiResults(data.results);
      setAiAlternativeResults(data.alternative_results || []);
      setAiRecommendationText(data.recommendation_text || "");
      setAiCriteria(data.criteria);
      setWeatherForecasts(data.weather_forecasts || {});
      setQuery("");
      setCountry("All Destinations");
      setSelectedTags([]);
    } catch (error) {
      setAiError("Start the Python search server, then try again.");
      setAiResults(null);
      setAiAlternativeResults([]);
      setAiRecommendationText("");
      setAiCriteria(null);
      setWeatherForecasts({});
    } finally {
      setIsAiSearching(false);
    }
  };

  const clearAll = () => {
    setQuery("");
    setCountry("All Destinations");
    setSelectedTags([]);
    setNaturalPrompt("");
    setAiResults(null);
    setAiAlternativeResults([]);
    setAiRecommendationText("");
    setAiCriteria(null);
    setAiError("");
    setWeatherForecasts({});
  };

  const visibleDestinations = aiResults || filteredDestinations;

  return (
    <>
      <Header />
      <main>
        <section className="hero">
          <div className="heroOverlay">
            <h1>Let's go somewhere</h1>
            <div className="searchShell">
              <div className="destinationField">
                <button
                  className="searchSegment destinationButton"
                  type="button"
                  onClick={() => setIsDestinationOpen((value) => !value)}
                >
                  <span>{country}</span>
                  <ChevronDown size={16} />
                </button>
                {isDestinationOpen && (
                  <div className="destinationMenu">
                    <button
                      type="button"
                      onClick={() => {
                        setCountry("All Destinations");
                        setIsDestinationOpen(false);
                      }}
                    >
                      All locations
                    </button>
                    <button type="button">Partner resorts</button>
                    {countries.map((item) => (
                      <button
                        type="button"
                        key={item}
                        onClick={() => {
                          setCountry(item);
                          setIsDestinationOpen(false);
                        }}
                        className={country === item ? "activeOption" : ""}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <input
                className="searchSegment searchInput"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by destination, country, or activity"
              />
              <div className="searchSegment staticSegment">Anytime</div>
              <div className="searchSegment staticSegment">2 guests</div>
              <button className="searchButton" type="button" aria-label="Search destinations">
                <Search size={22} />
              </button>
            </div>
            <form className="naturalSearch" onSubmit={handleNaturalSearch}>
              <div className="naturalInputWrap">
                <Bot size={20} />
                <input
                  value={naturalPrompt}
                  onChange={(event) => setNaturalPrompt(event.target.value)}
                  placeholder="Try: I want one week in early June somewhere with beach and biking"
                />
              </div>
              <button type="submit" disabled={isAiSearching}>
                {isAiSearching ? "Searching..." : "Find matches"}
              </button>
            </form>
            {aiError && <p className="aiError">{aiError}</p>}
          </div>
          <span className="heroCaption">Albufeira, Portugal</span>
        </section>

        <section className="results">
          <div className="breadcrumbs">Home / All Destinations</div>
          <div className="resultsHeader">
            <div>
              <h2>All Destinations</h2>
              <p>
                {visibleDestinations.length} resort
                {visibleDestinations.length === 1 ? "" : "s"} found
              </p>
            </div>
            <div className="resultActions">
              <button className="filterButton" type="button" onClick={() => setIsFilterOpen(true)}>
                <SlidersHorizontal size={18} />
                Add filter
                {selectedTags.length > 0 && <span>{selectedTags.length}</span>}
              </button>
              {(query || country !== "All Destinations" || selectedTags.length > 0 || aiResults) && (
                <button className="clearLink" type="button" onClick={clearAll}>
                  Clear all
                </button>
              )}
            </div>
          </div>

          {aiCriteria && (
            <div className="aiCriteria">
              <span>Trip criteria</span>
              <div>
                {aiCriteria.tags.map((tag) => (
                  <strong key={tag}>{tag}</strong>
                ))}
                {aiCriteria.duration_days && <strong>{aiCriteria.duration_days} days</strong>}
                {aiCriteria.date_window && <strong>{aiCriteria.date_window}</strong>}
                {aiCriteria.countries.map((item) => (
                  <strong key={item}>{item}</strong>
                ))}
                {aiCriteria.semantic_intent.map((item) => (
                  <strong key={item}>{item}</strong>
                ))}
                {!aiCriteria.used_llm && <strong>Local fallback</strong>}
              </div>
            </div>
          )}

          {aiRecommendationText && visibleDestinations.length > 0 && (
            <div className="aiRecommendationText">
              <Bot size={18} />
              <p>{aiRecommendationText}</p>
            </div>
          )}

          <div className="cardList">
            {visibleDestinations.map((destination) => (
              <DestinationCard
                destination={destination}
                key={destination.id}
                weather={weatherForecasts[destination.id]}
              />
            ))}
          </div>

          {visibleDestinations.length === 0 && aiResults && (
            <div className="noAiMatches">
              <div className="aiRecommendationText">
                <Bot size={18} />
                <p>
                  {aiRecommendationText ||
                    "There are no exact matching destinations for this request. Here are similar destinations available in our list."}
                </p>
              </div>

              {aiAlternativeResults.length > 0 && (
                <>
                  <h3>Similar available destinations</h3>
                  <div className="cardList">
                    {aiAlternativeResults.map((destination) => (
                      <DestinationCard
                        destination={destination}
                        key={destination.id}
                        weather={weatherForecasts[destination.id]}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

        </section>
      </main>

      {isFilterOpen && (
        <FilterModal
          selectedTags={selectedTags}
          onClose={() => setIsFilterOpen(false)}
          onToggleTag={toggleTag}
          onClear={clearAll}
        />
      )}
    </>
  );
}

const WMO_ICONS = {
  0: Sun, 1: Sun, 2: CloudSun, 3: Cloud,
  45: CloudFog, 48: CloudFog,
  51: Droplets, 53: Droplets, 55: Droplets,
  56: Droplets, 57: Droplets,
  61: CloudRain, 63: CloudRain, 65: CloudRain,
  66: CloudRain, 67: CloudRain,
  71: Snowflake, 73: Snowflake, 75: Snowflake,
  77: Snowflake,
  80: CloudRain, 81: CloudRain, 82: CloudRain,
  85: Snowflake, 86: Snowflake,
  95: CloudLightning, 96: CloudLightning, 99: CloudLightning,
};

const WMO_LABELS = {
  0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
  45: "Foggy", 48: "Foggy",
  51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
  61: "Light rain", 63: "Rain", 65: "Heavy rain",
  71: "Light snow", 73: "Snow", 75: "Heavy snow",
  80: "Showers", 81: "Showers", 82: "Heavy showers",
  95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
};

function WeatherStrip({ weather }) {
  if (!weather || !weather.dates || weather.dates.length === 0) return null;

  const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  return (
    <div className="weatherStrip">
      <div className="weatherStripHeader">
        <Thermometer size={14} />
        <span>Weather forecast</span>
      </div>
      <div className="weatherDays">
        {weather.dates.map((date, index) => {
          const d = new Date(date + "T00:00:00");
          const dayName = dayNames[d.getDay()];
          const dayNum = d.getDate();
          const code = weather.weather_code?.[index] ?? 0;
          const IconComponent = WMO_ICONS[code] || Cloud;
          const label = WMO_LABELS[code] || "";
          const tempMax = Math.round(weather.temp_max?.[index] ?? 0);
          const tempMin = Math.round(weather.temp_min?.[index] ?? 0);
          const rain = weather.precipitation_probability?.[index] ?? 0;

          return (
            <div className="weatherDay" key={date} title={label}>
              <span className="weatherDayName">{dayName} {dayNum}</span>
              <IconComponent size={18} className="weatherIcon" />
              <span className="weatherTemp">{tempMax}° / {tempMin}°</span>
              {rain > 0 && (
                <span className="weatherRain">
                  <Droplets size={10} /> {rain}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DestinationCard({ destination, weather }) {
  return (
    <article className="destinationCard">
      <img src={destination.image} alt={destination.name} />
      <div className="cardBody">
        <span className="location">
          {destination.location}, {destination.country}
        </span>
        <h3>{destination.name}</h3>
        <p>{destination.description}</p>
        {destination.reasons && (
          <p className="matchReasons">{destination.reasons.join(" / ")}</p>
        )}
        <WeatherStrip weather={weather} />
        <div className="tagList">
          {destination.tags.slice(0, 5).map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      </div>
      <div className="bookingPanel">
        <p>{destination.bookingText}</p>
        <button type="button">Explore Options</button>
      </div>
    </article>
  );
}

function Header() {
  return (
    <header className="siteHeader">
      <a className="logo" href="#top">HAPIMAG</a>
      <nav>
        <a href="#resorts">Resorts</a>
        <a href="#availability">Availability overview</a>
        <a href="#concept">Our concept</a>
        <a href="#membership">Membership</a>
        <a href="#try">Try out Hapimag</a>
      </nav>
      <div className="headerActions">
        <span>EUR</span>
        <span>EN</span>
        <a href="#signin">Sign in</a>
      </div>
    </header>
  );
}

function FilterModal({ selectedTags, onClose, onToggleTag, onClear }) {
  const topTags = filterTags.slice(0, 6);
  const activityTags = filterTags.slice(6);

  return (
    <div className="modalBackdrop">
      <div className="filterModal" role="dialog" aria-modal="true" aria-labelledby="filterTitle">
        <div className="modalHeader">
          <h2 id="filterTitle">Filters</h2>
          <button type="button" onClick={onClose} aria-label="Close filters">
            <X size={22} />
          </button>
        </div>

        <div className="iconFilters">
          {topTags.map((tag) => (
            <button
              type="button"
              key={tag}
              className={selectedTags.includes(tag) ? "selectedIconFilter" : ""}
              onClick={() => onToggleTag(tag)}
            >
              <span>{iconForTag(tag)}</span>
              {tag}
            </button>
          ))}
        </div>

        <h3>Activities</h3>
        <div className="checkboxList">
          {activityTags.map((tag) => (
            <label key={tag}>
              <input
                type="checkbox"
                checked={selectedTags.includes(tag)}
                onChange={() => onToggleTag(tag)}
              />
              <span>{tag}</span>
            </label>
          ))}
        </div>

        <div className="modalFooter">
          <button type="button" onClick={onClear}>
            Clear all
          </button>
          <button className="showButton" type="button" onClick={onClose}>
            Show resorts
          </button>
        </div>
      </div>
    </div>
  );
}

function iconForTag(tag) {
  const icons = {
    "Family friendly": "HH",
    "Pure nature": "/\\",
    Beach: "~~",
    "Culture & heritage": "[]",
    Wellness: "oo",
    "City trip": "##",
  };

  return icons[tag] || "*";
}

export default App;
