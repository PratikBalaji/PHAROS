"""Read-only stdio MCP interface. PHAROS_STAGE selects the synthetic exercise."""
import os
from mcp.server.fastmcp import FastMCP
from .core import tool_result

mcp=FastMCP('PHAROS wildfire exercise')
def stage():
    value=int(os.getenv('PHAROS_STAGE','0'))
    if value not in (0,1,2): raise ValueError('PHAROS_STAGE must be 0, 1 or 2')
    return value
@mcp.tool()
def get_incident_evidence() -> dict:
    """Return explicitly synthetic camera/satellite evidence and limitations."""
    return tool_result('get_incident_evidence',stage())
@mcp.tool()
def get_weather_context() -> dict:
    """Return scenario wind context; not a fire-spread prediction."""
    return tool_result('get_weather_context',stage())
@mcp.tool()
def get_candidate_routes() -> dict:
    """Return synthetic schematic routes, never real navigation instructions."""
    return tool_result('get_candidate_routes',stage())
@mcp.tool()
def check_route_constraints() -> dict:
    """Check scenario route segments against supplied synthetic hazard circles."""
    return tool_result('check_route_constraints',stage())
if __name__=='__main__': mcp.run(transport='stdio')
