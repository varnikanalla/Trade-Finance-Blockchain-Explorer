"""
External Data Integration Service - Week 7
Integrates with public trade/economic data sources
"""
import httpx
from typing import Dict, Optional
from datetime import datetime
import random  # For mock data


class ExternalDataService:
    """
    Integrate with external data sources for risk assessment:
    - UNCTAD (United Nations Conference on Trade and Development)
    - WTO (World Trade Organization)
    - BIS (Bank for International Settlements)
    """
    
    def __init__(self):
        self.timeout = 10.0
        
    async def get_unctad_trade_stats(self, country_code: str) -> Dict:
        """
        Fetch trade statistics from UNCTAD
        API: https://unctadstat.unctad.org/
        """
        # Mock implementation - replace with real API
        # Real API example:
        # url = f"https://unctadstat.unctad.org/wds/ReportFolders/reportFolders.aspx"
        # params = {"sCS_ChosenLang": "en", "sCountry": country_code}
        
        return {
            "country": country_code,
            "trade_volume_usd": random.randint(100_000_000, 10_000_000_000),
            "export_growth_rate": round(random.uniform(-5.0, 15.0), 2),
            "import_growth_rate": round(random.uniform(-5.0, 15.0), 2),
            "trade_balance": round(random.uniform(-1000, 1000), 2),
            "year": 2024,
            "source": "UNCTAD (Mock Data)",
            "fetched_at": datetime.utcnow().isoformat()
        }
    
    async def get_wto_trade_indicators(self, country_code: str) -> Dict:
        """
        Fetch WTO trade policy indicators
        API: https://api.wto.org/
        """
        # Mock implementation
        # Real WTO API requires registration and API key
        
        return {
            "country": country_code,
            "tariff_rate_avg": round(random.uniform(2.0, 15.0), 2),
            "trade_facilitation_score": round(random.uniform(50.0, 95.0), 2),
            "wto_member": random.choice([True, False]),
            "trade_disputes_count": random.randint(0, 20),
            "compliance_rating": random.choice(["high", "medium", "low"]),
            "source": "WTO (Mock Data)",
            "fetched_at": datetime.utcnow().isoformat()
        }
    
    async def get_bis_banking_stats(self, country_code: str) -> Dict:
        """
        Fetch banking/financial stability data from BIS
        API: https://data.bis.org/
        """
        # Mock implementation
        # Real BIS data available through their Statistics API
        
        return {
            "country": country_code,
            "banking_stability_index": round(random.uniform(40.0, 90.0), 2),
            "credit_to_gdp_ratio": round(random.uniform(50.0, 250.0), 2),
            "foreign_exchange_reserves": random.randint(10, 500),  # Billions USD
            "default_risk_score": round(random.uniform(10.0, 80.0), 2),
            "source": "BIS (Mock Data)",
            "fetched_at": datetime.utcnow().isoformat()
        }
    
    async def get_worldbank_indicators(self, country_code: str) -> Dict:
        """
        Fetch economic indicators from World Bank Open Data
        API: https://api.worldbank.org/v2/
        """
        # Mock implementation
        # Real API: https://api.worldbank.org/v2/country/{code}/indicator/{indicator}
        
        return {
            "country": country_code,
            "gdp_growth": round(random.uniform(-3.0, 8.0), 2),
            "gdp_per_capita": random.randint(5000, 70000),
            "inflation_rate": round(random.uniform(0.5, 12.0), 2),
            "unemployment_rate": round(random.uniform(3.0, 25.0), 2),
            "ease_of_doing_business_rank": random.randint(1, 190),
            "corruption_perception_index": round(random.uniform(20.0, 90.0), 2),
            "year": 2024,
            "source": "World Bank (Mock Data)",
            "fetched_at": datetime.utcnow().isoformat()
        }
    
    async def get_composite_risk_data(self, country_code: str) -> Dict:
        """
        Fetch and combine data from multiple sources
        """
        try:
            # In production, make these requests concurrently
            unctad = await self.get_unctad_trade_stats(country_code)
            wto = await self.get_wto_trade_indicators(country_code)
            bis = await self.get_bis_banking_stats(country_code)
            worldbank = await self.get_worldbank_indicators(country_code)
            
            # Calculate composite risk score
            composite_score = self._calculate_composite_risk(
                unctad, wto, bis, worldbank
            )
            
            return {
                "country": country_code,
                "composite_risk_score": composite_score,
                "data_sources": {
                    "unctad": unctad,
                    "wto": wto,
                    "bis": bis,
                    "worldbank": worldbank
                },
                "aggregated_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "error": str(e),
                "country": country_code,
                "composite_risk_score": 50,  # Default moderate risk
                "fallback": True
            }
    
    def _calculate_composite_risk(self, unctad: Dict, wto: Dict, 
                                   bis: Dict, worldbank: Dict) -> float:
        """
        Calculate composite risk score from multiple data sources
        Returns: 0-100 (lower is better)
        """
        risk_factors = []
        
        # Trade balance risk (negative balance = higher risk)
        if unctad["trade_balance"] < -500:
            risk_factors.append(60)
        elif unctad["trade_balance"] < 0:
            risk_factors.append(40)
        else:
            risk_factors.append(20)
        
        # Tariff rate (higher tariffs = higher risk for trade)
        risk_factors.append(min(100, wto["tariff_rate_avg"] * 5))
        
        # Banking stability (inverse: lower stability = higher risk)
        risk_factors.append(100 - bis["banking_stability_index"])
        
        # Economic indicators
        if worldbank["gdp_growth"] < 0:
            risk_factors.append(70)
        elif worldbank["gdp_growth"] < 2:
            risk_factors.append(50)
        else:
            risk_factors.append(30)
        
        # Inflation risk
        if worldbank["inflation_rate"] > 10:
            risk_factors.append(80)
        elif worldbank["inflation_rate"] > 5:
            risk_factors.append(50)
        else:
            risk_factors.append(20)
        
        # Average all risk factors
        return round(sum(risk_factors) / len(risk_factors), 2)
    
    async def get_realtime_forex_rates(self, base_currency: str = "USD") -> Dict:
        """
        Get real-time foreign exchange rates
        Could use: exchangerate-api.com, fixer.io, or openexchangerates.org
        """
        # Mock implementation
        currencies = ["EUR", "GBP", "JPY", "CNY", "INR", "BRL"]
        rates = {}
        for currency in currencies:
            rates[currency] = round(random.uniform(0.5, 150.0), 4)
        
        return {
            "base": base_currency,
            "rates": rates,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "Mock FX Data"
        }
    
    async def get_sanctions_check(self, entity_name: str, country: str) -> Dict:
        """
        Check if entity is on sanctions lists (OFAC, UN, EU, etc.)
        In production: integrate with compliance APIs
        """
        # Mock implementation
        # Real APIs: ComplyAdvantage, Refinitiv World-Check, etc.
        
        is_sanctioned = random.random() < 0.05  # 5% chance for demo
        
        return {
            "entity": entity_name,
            "country": country,
            "is_sanctioned": is_sanctioned,
            "lists_checked": ["OFAC", "UN Security Council", "EU Sanctions"],
            "risk_level": "high" if is_sanctioned else "low",
            "checked_at": datetime.utcnow().isoformat(),
            "source": "Mock Sanctions Data"
        }


# Real API Integration Examples (commented out):
"""
# Example: Real UNCTAD API call
async def get_unctad_trade_stats_real(country_code: str):
    async with httpx.AsyncClient() as client:
        url = "https://unctadstat.unctad.org/api/GetData"
        params = {
            "country": country_code,
            "indicator": "TRADE_VALUE",
            "year": "latest"
        }
        response = await client.get(url, params=params, timeout=10.0)
        return response.json()

# Example: Real World Bank API call
async def get_worldbank_real(country_code: str, indicator: str):
    async with httpx.AsyncClient() as client:
        url = f"https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator}"
        params = {"format": "json", "per_page": 1, "date": "latest"}
        response = await client.get(url, params=params, timeout=10.0)
        return response.json()

# Example: Real FX rates from exchangerate-api.com
async def get_forex_rates_real(api_key: str, base: str = "USD"):
    async with httpx.AsyncClient() as client:
        url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}"
        response = await client.get(url, timeout=10.0)
        return response.json()
"""
