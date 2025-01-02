from flask import Flask, jsonify, abort
from flask_cors import CORS
from flasgger import Swagger
from sqlalchemy import create_engine
from sqlalchemy import cast, Integer
from sqlalchemy import func, case
from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_
import os
from models.base import Base
from models.scores import *
from models.draft import *
from models.transactions import *
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.config['SWAGGER'] = {
    'title': 'Fantasy FiM API',
    'uiversion': 3,
    'specs': [
        {
            'endpoint': 'apispec_1',
            'route': '/api/apidocs/swagger.json',
            'rule_filter': lambda rule: True,  # All rules are included
            'model_filter': lambda tag: True  # All models are included
        }
    ],
    'headers': [],
    'static_url_path': '/apidocs',
}

swagger_config = Swagger.DEFAULT_CONFIG
swagger_config['swagger_ui_bundle_js'] = '//unpkg.com/swagger-ui-dist@3/swagger-ui-bundle.js'
swagger_config['swagger_ui_standalone_preset_js'] = '//unpkg.com/swagger-ui-dist@3/swagger-ui-standalone-preset.js'
swagger_config['jquery_js'] = '//unpkg.com/jquery@2.2.4/dist/jquery.min.js'
swagger_config['swagger_ui_css'] = '//unpkg.com/swagger-ui-dist@3/swagger-ui.css'
swagger_config['specs_route'] = "/api/apidocs/"

swagger = Swagger(app, 
    template={
        "swagger": "2.0",
        "info": {
            "title": "Fantasy FiM API",
            "description": "API documentation",
            "version": "1.0.0",
        },
        "host": "fantasyfim.com",  # Update with your host
        "basePath": "/api",        # This should match your API prefix
    },
    config=swagger_config
)
CORS(app)

# Configure the database
DATABASE_URL = os.getenv("DATABASE_URL")  # or your database URL
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

@app.route('/api/leagues', methods=['GET'])
def get_leagues():
    """
    Retrieve a list of active leagues.
    ---
    tags:
        - Leagues

    responses:
      200:
        description: A list of active leagues.
        schema:
          type: array
          items:
            properties:
              league_id:
                type: integer
                example: 1
              league_name:
                type: string
                example: "FRC 2024"
              year:
                type: integer
                example: 2024
              team_limit:
                type: integer
                example: 10
              team_starts:
                type: integer
                example: 5
              is_fim:
                type: boolean
                example: true
              offseason:
                type: boolean
                example: false
              team_size_limit:
                type: integer
                example: 6
      500:
        description: Internal server error.
    """
    session = Session()
    leagues = session.query(League).filter(League.active==True).all()
    session.close()
    
    return jsonify([{
        "league_id": league.league_id,
        "league_name": league.league_name,
        "year": league.year,
        "team_limit": league.team_limit,
        "team_starts": league.team_starts,
        "is_fim": league.is_fim,
        "offseason": league.offseason,
        "team_size_limit": league.team_size_limit
    } for league in leagues])

@app.route('/api/leagues/<int:leagueId>', methods=['GET'])
def get_league(leagueId):
    """
    Retrieve a league's data.
    ---
    tags:
        - Leagues
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: The ID of the league for which to retrieve data from.
    responses:
      200:
        description: An active league.
        schema:
          type: array
          items:
            properties:
              league_id:
                type: integer
                example: 1
              league_name:
                type: string
                example: "FRC 2025"
              weekly_starts:
                type: int
                example: 3
              year:
                type: int
                example: 2025
              is_fim:
                type: bool
                example: True
      500:
        description: Internal server error.
    """
    session = Session()
    league = session.query(League).filter(League.active==True, League.league_id==leagueId).first()
    session.close()
    return jsonify({"league_id": league.league_id, "league_name": league.league_name, "weekly_starts": league.team_starts, "year": league.year, "is_fim": league.is_fim} )

@app.route('/api/leagues/<int:leagueId>/fantasyTeams', methods=['GET'])
def get_fantasy_teams(leagueId):
    """
    Retrieve a list of fantasy teams for a specific league.
    ---
    tags:
        - Leagues
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: The ID of the league for which to retrieve fantasy teams.
    responses:
      200:
        description: A list of fantasy teams for the specified league.
        schema:
          type: array
          items:
            properties:
              fantasy_team_id:
                type: integer
                example: 1
              team_name:
                type: string
                example: "Team Awesome"
      404:
        description: League not found.
      500:
        description: Internal server error.
    """
    session = Session()
    teams = session.query(FantasyTeam).filter(FantasyTeam.league_id==leagueId).order_by(FantasyTeam.fantasy_team_id.asc()).all()
    session.close()
    return jsonify([{"fantasy_team_id": team.fantasy_team_id, "team_name": team.fantasy_team_name} for team in teams])

@app.route('/api/leagues/<int:leagueId>/teamsOnWaivers', methods=['GET'])
def get_waiver_teams(leagueId):
    """
    Retrieve a list of teams on waivers for a specific league, including their registered events and Statbotics data. 
    This will only return data if league.is_fim is True.
    ---
    tags:
        - Leagues
        - Waivers
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: The ID of the league for which to retrieve teams on waivers.
    responses:
      200:
        description: A list of teams on waivers for the specified league, including events and Statbotics data.
        schema:
          type: array
          items:
            type: object
            properties:
              team_number:
                type: integer
                description: The number of the available team.
              name:
                type: string
                description: The name of the team.
              events:
                type: array
                items:
                  type: object
                  properties:
                    event_key:
                      type: string
                      description: The key of the event.
                    week:
                      type: integer
                      description: The week of the event.
      404:
        description: League not found.
    """
    # Create a new session
    with Session() as session:
        # Retrieve the league to ensure it exists
        league = session.query(League).filter(League.league_id == leagueId).first()

        if league is None:
            abort(404, description="League not found")

        if not league.is_fim:
            session.close()
            return jsonify([])

        year = league.year

        # Query to retrieve teams on waivers along with their data, ordered by team_number casted as an integer
        waiver_teams_query = session.query(
            Team.team_number,
            Team.name,  # Add team name
            FRCEvent.event_key,
            FRCEvent.week,
        ).join(TeamOnWaivers, Team.team_number == TeamOnWaivers.team_number).join(
            TeamScore, Team.team_number == TeamScore.team_key
        ).join(
            FRCEvent, TeamScore.event_key == FRCEvent.event_key
        ).filter(
            TeamOnWaivers.league_id == leagueId,
            FRCEvent.year == year
        ).order_by(
            cast(Team.team_number, Integer).asc()  # Cast team_number to Integer for sorting
        ).all()

        # Prepare the teams on waivers list with events and Statbotics data
        waiver_teams = {}

        for row in waiver_teams_query:
            team_number = row.team_number
            team_name = row.name  # Get the team name
            event_key = row.event_key
            week = row.week

            if team_number not in waiver_teams:
                waiver_teams[team_number] = {
                    "team_number": team_number,
                    "name": team_name,  # Include team name
                    "events": []
                }

            waiver_teams[team_number]["events"].append({"event_key": event_key, "week": week})

        # Return the list of teams on waivers
        return jsonify(list(waiver_teams.values()))

@app.route('/api/leagues/<int:leagueId>/rosters', methods=["GET"])
def get_rosters(leagueId):
    """
    Retrieve the rosters for all fantasy teams in a specific league. Will only return data if league is_fim.
    ---
    tags:
        - Leagues
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: The ID of the league for which to retrieve team rosters.
    responses:
      200:
        description: A list of rosters for all fantasy teams in the specified league.
        schema:
          type: array
          items:
            properties:
              fantasy_team_id:
                type: integer
                example: 1
              fantasy_team_name:
                type: string
                example: "Team Awesome"
              roster:
                type: array
                items:
                  type: string
                  example: "frc1234"
      404:
        description: League not found.
      500:
        description: Internal server error.
    """
    session = Session()
    # Retrieve the league to ensure it exists
    league = session.query(League).filter(League.league_id == leagueId).first()

    if league is None:
        abort(404, description="League not found")

    if not league.is_fim:
        session.close()
        return jsonify([])
    
    teams = session.query(FantasyTeam).filter(FantasyTeam.league_id==leagueId).order_by(FantasyTeam.fantasy_team_id.asc()).all()
    teamsOwnedInLeague = session.query(TeamOwned).filter(TeamOwned.league_id==leagueId)
    output = []
    for team in teams:
        output.append({"fantasy_team_id":team.fantasy_team_id,\
                       "fantasy_team_name":team.fantasy_team_name,\
                        "roster": [frcteam.team_key for frcteam in teamsOwnedInLeague.filter(TeamOwned.fantasy_team_id==team.fantasy_team_id).all()]})
    session.close()
    return jsonify(output)

@app.route('/api/leagues/<int:leagueId>/rosterWeeks', methods=["GET"])
def get_roster_weeks(leagueId):
    """
    Retrieve the weeks and events for teams on every fantasy team's roster in a specific league.
    Only returns data if the league is_fim.
    ---
    tags:
        - Leagues
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: The ID of the league for which to retrieve roster weeks and events.
    responses:
      200:
        description: A list of rosters for all fantasy teams in the specified league, including the weeks and events their teams are competing in.
        schema:
          type: array
          items:
            properties:
              fantasy_team_id:
                type: integer
                example: 1
              fantasy_team_name:
                type: string
                example: "Team Awesome"
              roster:
                type: array
                items:
                  type: object
                  properties:
                    team_key:
                      type: string
                      example: "frc1234"
                    events:
                      type: array
                      items:
                        type: object
                        properties:
                          event_key:
                            type: string
                            example: "2023miket"
                          event_name:
                            type: string
                            example: "Kettering University Event"
                          week:
                            type: integer
                            example: 2
      404:
        description: League not found.
      500:
        description: Internal server error.
    """
    session = Session()
    # Retrieve the league to ensure it exists
    league = session.query(League).filter(League.league_id == leagueId).first()

    if league is None:
        abort(404, description="League not found")

    if not league.is_fim:
        session.close()
        return jsonify([])
    
    teams = session.query(FantasyTeam).filter(FantasyTeam.league_id == leagueId).order_by(FantasyTeam.fantasy_team_id.asc()).all()
    teamsOwnedInLeague = session.query(TeamOwned).filter(TeamOwned.league_id == leagueId)
    
    output = []
    
    for team in teams:
        team_roster = teamsOwnedInLeague.filter(TeamOwned.fantasy_team_id == team.fantasy_team_id).all()
        roster_output = []
        
        for frcteam in team_roster:
            # Retrieve the events the team is competing in
            events = session.query(FRCEvent)\
                .join(TeamScore, TeamScore.event_key == FRCEvent.event_key)\
                .filter(TeamScore.team_key == frcteam.team_key)\
                .filter(FRCEvent.year == league.year)\
                .filter(FRCEvent.week < 6)\
                .all()

            event_details = [{"event_key": event.event_key, "event_name": event.event_name, "week": event.week} for event in events]

            
            roster_output.append({
                "team_key": frcteam.team_key,
                "events": event_details
            })
        
        output.append({
            "fantasy_team_id": team.fantasy_team_id,
            "fantasy_team_name": team.fantasy_team_name,
            "roster": roster_output
        })
    
    session.close()
    return jsonify(output)

@app.route('/api/drafts/<int:draftId>/picks', methods=["GET"])
def get_draft_picks(draftId):
    """
    Retrieve a list of draft picks for a specific draft, including the events teams compete in with their weeks. Will not return week data if league.is_fim is false
    ---
    tags:
        - Drafts
    parameters:
      - name: draftId
        in: path
        type: integer
        required: true
        description: The ID of the draft for which to retrieve draft picks.
    responses:
      200:
        description: A list of draft picks for the specified draft with their events.
        schema:
          type: array
          items:
            properties:
              pick_number:
                type: integer
                example: 1
              fantasy_team_id:
                type: integer
                example: 2
              team_picked:
                type: string
                example: "frc1234"
              events:
                type: array
                items:
                  type: object
                  properties:
                    event_key:
                      type: string
                      example: "2023txda"
                    week:
                      type: integer
                      example: 3
      404:
        description: Draft not found.
      500:
        description: Internal server error.
    """
    session = Session()
    
    # Query for draft picks
    draft_picks = session.query(DraftPick).filter(DraftPick.draft_id == draftId).order_by(DraftPick.pick_number.asc()).all()

    draft: Draft = session.query(Draft).filter(Draft.draft_id==draftId).first()
    league: League = draft.league

    if not draft_picks:
        session.close()
        return jsonify({"error": "Draft not found"}), 404

    # Collect draft pick details with team events
    picks_data = []
    for pick in draft_picks:
        team_events = (
            session.query(TeamScore.event_key, FRCEvent.week)
            .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key)
            .filter(TeamScore.team_key == pick.team_number)
            .filter(FRCEvent.year == league.year)
            .all()
        )
        
        # Retrieve the league information
        league = session.query(League).filter(League.league_id == draft.league_id).first()

        
        events = None
        # Format team events into the desired structure
        if league.is_fim:
          events = [{"event_key": event.event_key, "week": event.week} for event in team_events]
        
        picks_data.append({
            "pick_number": pick.pick_number,
            "fantasy_team_id": pick.fantasy_team_id,
            "team_picked": pick.team_number,
            "events": events
        })
    
    session.close()

    return jsonify(picks_data)

@app.route('/api/drafts/<int:draftId>/draftOrder', methods=['GET'])
def get_draft_order(draftId):
    """
    Get Draft Order for a Specific Draft
    ---
    tags:
      - Drafts
    parameters:
      - name: draftId
        in: path
        type: integer
        required: true
        description: The ID of the draft to retrieve the order for
    responses:
      200:
        description: A list of fantasy teams with their draft slots for the specified draft
        schema:
          type: array
          items:
            type: object
            properties:
              fantasy_team_id:
                type: integer
                description: The ID of the fantasy team
              draft_slot:
                type: integer
                description: The slot of the team in the draft
      404:
        description: Draft not found
    """
    session = Session()
    
    # Query draft order for the specified draftId
    draft_order = session.query(DraftOrder).filter(DraftOrder.draft_id == draftId).order_by(DraftOrder.draft_slot.asc()).all()
    session.close()

    if not draft_order:
        return jsonify({"error": "Draft not found"}), 404

    # Convert the DraftOrder objects to a list of dictionaries for the JSON response
    return jsonify([{
        "fantasy_team_id": draft.fantasy_team_id,
        "draft_slot": draft.draft_slot
    } for draft in draft_order])

@app.route('/api/leagues/<int:leagueId>/lineups', methods=['GET'])
def get_lineups(leagueId):
    """
    Retrieve the lineups for all fantasy teams in a specified league for all weeks.

    ---
    tags:
      - Leagues
    parameters:
      - name: leagueId
        in: path
        required: true
        description: The ID of the league to retrieve lineups for.
        type: integer
    responses:
      200:
        description: A list of weeks with fantasy teams and their lineups.
        schema:
          type: array
          items:
            type: object
            properties:
              week:
                type: integer
                description: The week number.
              fantasy_teams:
                type: array
                items:
                  type: object
                  properties:
                    fantasy_team_id:
                      type: integer
                      description: The ID of the fantasy team.
                    fantasy_team_name:
                      type: string
                      description: The name of the fantasy team.
                    teams:
                      type: array
                      items:
                        type: object
                        properties:
                          team_number:
                            type: string
                            description: The number of the team started.
      404:
        description: No fantasy teams found for the specified league.
      500:
        description: Internal server error.
    """
    session = Session()

    # Query to get all fantasy teams for the given league
    fantasy_teams = session.query(FantasyTeam).filter(
        FantasyTeam.league_id == leagueId
    ).all()

    # Query to get all team started records for the given league
    started_teams = session.query(TeamStarted).filter(
        TeamStarted.fantasy_team_id.in_([ft.fantasy_team_id for ft in fantasy_teams])
    ).all()

    # Organizing the output by week
    output = {}
    
    for week in range(1, 7):  # Weeks 1 to 6 (including MSC week)
        output[week] = {
            "week": week,
            "fantasy_teams": []
        }

        # Populate each fantasy team entry
        for fantasy_team in fantasy_teams:
            fantasy_team_entry = {
                "fantasy_team_id": fantasy_team.fantasy_team_id,
                "fantasy_team_name": fantasy_team.fantasy_team_name,
                "teams": []
            }

            # Find all started teams for the current week
            for started_team in started_teams:
                if started_team.fantasy_team_id == fantasy_team.fantasy_team_id and started_team.week == week:
                    fantasy_team_entry["teams"].append({
                        "team_number": started_team.team_number
                    })

            # Append the fantasy team entry to the week
            output[week]["fantasy_teams"].append(fantasy_team_entry)

    session.close()
    
    # Transform output to a list of weeks
    final_output = list(output.values())

    if not final_output:
        return jsonify([]), 404  # Return an empty list if no teams found

    return jsonify(final_output), 200

@app.route('/api/leagues/<int:leagueId>/fantasyScores/<int:week>', methods=['GET'])
def get_fantasy_scores(leagueId, week):
    """
    Retrieve the fantasy scores for all fantasy teams in a specified league for a specific week.

    ---
    tags:
      - FantasyScores
    parameters:
      - name: leagueId
        in: path
        required: true
        description: The ID of the league to retrieve fantasy scores for.
        type: integer
      - name: week
        in: path
        required: true
        description: The week for which to retrieve the fantasy scores.
        type: integer
    responses:
      200:
        description: A list of fantasy teams with their weekly scores and breakdown of teams started.
        schema:
          type: array
          items:
            type: object
            properties:
              fantasy_team_id:
                type: integer
                description: The ID of the fantasy team.
              fantasy_team_name:
                type: string
                description: The name of the fantasy team.
              weekly_score:
                type: integer
                description: The total score of the fantasy team for the week.
              rank_points:
                type: integer
                description: Ranking points for the fantasy team.
              week:
                type: integer
                description: The week number for which the scores are being retrieved.
              teams:
                type: array
                items:
                  type: object
                  properties:
                    team_number:
                      type: string
                      description: The number of the team started.
                    weekly_score:
                      type: integer
                      description: The total score of the team for the week.
                    breakdown:
                      type: object
                      properties:
                        qual_points:
                          type: integer
                          description: Qualification points scored by the team.
                        alliance_points:
                          type: integer
                          description: Alliance points scored by the team.
                        elim_points:
                          type: integer
                          description: Elimination points scored by the team.
                        award_points:
                          type: integer
                          description: Award points scored by the team.
                        rookie_points:
                          type: integer
                          description: Rookie points scored by the team.
                        stat_correction:
                          type: integer
                          description: Statistical corrections applied to the team's score.
      404:
        description: No fantasy teams found for the specified league and week.
      500:
        description: Internal server error.
    """
    session = Session()
    
    # Query to get fantasy scores for the given league and week
    fantasy_scores = session.query(FantasyScores).filter(
        FantasyScores.league_id == leagueId,
        FantasyScores.week == week
    ).order_by(FantasyScores.fantasy_team_id.asc()).all()
    
    # Prepare the output
    output = []
    for score in fantasy_scores:
        # Get the fantasy team details
        fantasy_team = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id == score.fantasy_team_id).first()
        
        # Get the teams started by this fantasy team for the specified week
        started_teams = session.query(TeamStarted).filter(
            TeamStarted.fantasy_team_id == score.fantasy_team_id,
            TeamStarted.week == week
        ).all()
        
        # Prepare a breakdown of scores
        team_scores_breakdown = []
        for started_team in started_teams:
            # Get the team score for the started team
            team_score = session.query(TeamScore).filter(
                TeamScore.team_key == started_team.team_number,
                TeamScore.event_key == started_team.event_key  # Assuming the event_key relates to the TeamScore table
            ).first()
            
            if team_score:
                team_scores_breakdown.append({
                    "team_number": started_team.team_number,
                    "weekly_score": team_score.score_team(),
                    "breakdown": {
                    "qual_points": team_score.qual_points,
                    "alliance_points": team_score.alliance_points,
                    "elim_points": team_score.elim_points,
                    "award_points": team_score.award_points,
                    "rookie_points": team_score.rookie_points,
                    "stat_correction": team_score.stat_correction
                    }  # Calculate total score using the method in TeamScore
                })
        
        # Append to the output if any teams were started
        if team_scores_breakdown:
            output.append({
                "fantasy_team_id": fantasy_team.fantasy_team_id,
                "fantasy_team_name": fantasy_team.fantasy_team_name,
                "weekly_score": score.weekly_score,
                "rank_points": score.rank_points,
                "week": week,
                "teams": team_scores_breakdown
            })
    
    session.close()
    return jsonify(output)

@app.route('/api/drafts/<int:draftId>/fantasyScores', methods=['GET'])
def get_draft_scores(draftId):
    """
    Retrieve the fantasy scores for all fantasy teams in a specified draft (use for single event leagues).

    ---
    tags:
      - Drafts
      - FantasyScores
    parameters:
      - name: draftId
        in: path
        required: true
        description: The ID of the draft to retrieve fantasy scores for.
        type: integer
    responses:
      200:
        description: A list of fantasy teams with their weekly scores and breakdown of teams started.
        schema:
          type: array
          items:
            type: object
            properties:
              fantasy_team_id:
                type: integer
                description: The ID of the fantasy team.
              fantasy_team_name:
                type: string
                description: The name of the fantasy team.
              event_score:
                type: integer
                description: The total score of the fantasy team for the drafted event.
              rank_points:
                type: integer
                description: Ranking points for the fantasy team.
              week:
                type: integer
                description: The week number for which the scores are being retrieved.
              teams:
                type: array
                items:
                  type: object
                  properties:
                    team_number:
                      type: string
                      description: The number of the team started.
                    event_score:
                      type: integer
                      description: The total score of the team for the event drafted.
                    breakdown:
                      type: object
                      properties:
                        qual_points:
                          type: integer
                          description: Qualification points scored by the team.
                        alliance_points:
                          type: integer
                          description: Alliance points scored by the team.
                        elim_points:
                          type: integer
                          description: Elimination points scored by the team.
                        award_points:
                          type: integer
                          description: Award points scored by the team.
                        rookie_points:
                          type: integer
                          description: Rookie points scored by the team.
                        stat_correction:
                          type: integer
                          description: Statistical corrections applied to the team's score.
      404:
        description: No fantasy teams found for the specified draft.
      500:
        description: Internal server error.
    """
    session = Session()
    draft: Draft = session.query(Draft).filter(Draft.draft_id==draftId).first()
    if not draft:
        abort(404, "No draft found.")

    league: League = draft.league
    if league.is_fim:
        abort(400, "Cannot make this request on a FiM league.")

    # Query to get fantasy scores for the given league
    fantasy_scores = session.query(FantasyScores).filter(
        FantasyScores.league_id == league.league_id,
        FantasyScores.event_key == draft.event_key
    ).order_by(FantasyScores.fantasy_team_id.asc()).all()
    
    # Prepare the output
    output = []
    for score in fantasy_scores:
        # Get the fantasy team details
        fantasy_team = session.query(FantasyTeam).filter(FantasyTeam.fantasy_team_id == score.fantasy_team_id).first()
        
        # Get the teams draft by this fantasy team for the specified draft
        drafted_teams = session.query(DraftPick).filter(
            DraftPick.fantasy_team_id == score.fantasy_team_id,
            DraftPick.draft_id == draftId
        ).all()
        
        # Prepare a breakdown of scores
        team_scores_breakdown = []
        for drafted_team in drafted_teams:
            # Get the team score for the started team
            team_score = session.query(TeamScore).filter(
                TeamScore.team_key == drafted_team.team_number,
                TeamScore.event_key == draft.event_key
            ).first()
            
            if team_score:
                team_scores_breakdown.append({
                    "team_number": drafted_team.team_number,
                    "event_score": team_score.score_team(),
                    "breakdown": {
                    "qual_points": team_score.qual_points,
                    "alliance_points": team_score.alliance_points,
                    "elim_points": team_score.elim_points,
                    "award_points": team_score.award_points,
                    "rookie_points": team_score.rookie_points,
                    "stat_correction": team_score.stat_correction
                    }  # Calculate total score using the method in TeamScore
                })
        
        # Append to the output if any teams were started
        if team_scores_breakdown:
            output.append({
                "fantasy_team_id": fantasy_team.fantasy_team_id,
                "fantasy_team_name": fantasy_team.fantasy_team_name,
                "event_score": score.weekly_score,
                "rank_points": score.rank_points,
                "week": draft.event.week,
                "teams": team_scores_breakdown
            })
    
    session.close()
    return jsonify(output)

@app.route('/api/leagues/<int:leagueId>/waiverPriority', methods=['GET'])
def get_waiver_priority(leagueId):
    """
    Get Waiver Priority for a Specific League, including Fantasy Team names. If league isn't FiM then return an empty array.
    ---
    tags:
      - Waivers
      - Leagues
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: The ID of the league to retrieve the waiver priority for
    responses:
      200:
        description: A list of fantasy teams with their waiver priority in the specified league
        schema:
          type: array
          items:
            type: object
            properties:
              fantasy_team_id:
                type: integer
                description: The ID of the fantasy team
              fantasy_team_name:
                type: string
                description: The name of the fantasy team
              priority:
                type: integer
                description: The waiver priority of the fantasy team
      404:
        description: League not found
    """
    # Create a new session
    with Session() as session:
        # Query waiver priority along with the fantasy team name for the specified leagueId

        # Retrieve the league to ensure it exists
        league = session.query(League).filter(League.league_id == leagueId).first()

        if league is None:
            abort(404, description="League not found")

        if not league.is_fim:
            session.close()
            return jsonify([])

        waiver_priority = session.query(
            WaiverPriority.fantasy_team_id,
            WaiverPriority.priority,
            FantasyTeam.fantasy_team_name  # Include the fantasy team name
        ).join(
            FantasyTeam, WaiverPriority.fantasy_team_id == FantasyTeam.fantasy_team_id
        ).filter(
            WaiverPriority.league_id == leagueId
        ).order_by(
            WaiverPriority.priority.asc()
        ).all()

        # Close the session
        session.close()

        # If no results found, return a 404 response
        if not waiver_priority:
            return jsonify({"error": "League not found or no waiver priorities"}), 404

        # Convert the results to a list of dictionaries for the JSON response
        return jsonify([{
            "fantasy_team_id": waiver.fantasy_team_id,
            "fantasy_team_name": waiver.fantasy_team_name,  # Include the fantasy team name in the response
            "priority": waiver.priority
        } for waiver in waiver_priority])

@app.route('/api/leagues/<int:leagueId>/rankings', methods=['GET'])
def get_league_rankings(leagueId):
    """
    Retrieve cumulative rankings per week for every team in a league, sorted by cumulative ranking points,
    only including weeks with finalized scores.
    ---
    tags:
      - Leagues
      - FantasyScores
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: ID of the league to retrieve rankings for.
    responses:
      200:
        description: A list of teams with their cumulative ranking points and weekly breakdowns.
        schema:
          type: array
          items:
            type: object
            properties:
              fantasy_team_id:
                type: integer
                description: The ID of the fantasy team.
              fantasy_team_name:
                type: string
                description: The name of the fantasy team.
              total_ranking_points:
                type: number
                description: Cumulative ranking points for the team.
              tiebreaker:
                type: number
                description: Cumulative weekly score for the team.
              weekly_scores:
                type: array
                items:
                  type: object
                  properties:
                    week:
                      type: integer
                      description: The week number.
                    ranking_points:
                      type: number
                      description: The ranking points for that week.
                    weekly_score:
                      type: integer
                      description: The weekly score for that week.
    """
    session = Session()

    # Query the league to get the league year
    league = session.query(League).filter(League.league_id == leagueId).first()
    
    if not league:
        session.close()
        return jsonify({"error": "League not found"}), 404

    # Query for the weeks with finalized scores for the league's year
    finalized_weeks = session.query(WeekStatus).filter(
        WeekStatus.year == league.year,
        WeekStatus.scores_finalized == True
    ).all()

    finalized_week_numbers = {week.week for week in finalized_weeks}

    # Query for the fantasy teams in the specified league
    fantasy_teams = session.query(FantasyTeam).filter(FantasyTeam.league_id == leagueId).all()

    result = []

    for team in fantasy_teams:
        # Get all the scores for the fantasy team, filtering by finalized weeks
        scores = session.query(FantasyScores).filter(
            FantasyScores.fantasy_team_id == team.fantasy_team_id,
            FantasyScores.week.in_(finalized_week_numbers)
        ).order_by(FantasyScores.week.asc()).all()

        total_ranking_points = sum(score.rank_points for score in scores)
        total_weekly_score = sum(score.weekly_score for score in scores)  # Calculate cumulative weekly score
        #TODO: incorporate scores for single-run events
        weekly_scores = [{"week": score.week,
                          "ranking_points": score.rank_points,
                          "weekly_score": score.weekly_score} for score in scores]

        result.append({
            "fantasy_team_id": team.fantasy_team_id,
            "fantasy_team_name": team.fantasy_team_name,
            "total_ranking_points": total_ranking_points,
            "tiebreaker": total_weekly_score,  # Add cumulative weekly score
            "weekly_scores": weekly_scores
        })

    # Sort by total ranking points and total weekly score
    result.sort(key=lambda x: (x["total_ranking_points"], x["tiebreaker"]), reverse=True)

    session.close()

    return jsonify(result)

@app.route('/api/leagues/<int:leagueId>/statesTeams', methods=['GET'])
def get_states_round_team_ids(leagueId):
    """
    Retrieve the top 3 fantasy team IDs in the states round based on total ranking points,
    evaluated only on weeks up to and including week 5.
    ---
    tags:
      - Leagues
      - FantasyScores
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: ID of the league to retrieve states round team IDs for.
    responses:
      200:
        description: A list of the top 3 fantasy team IDs in the states round.
        schema:
          type: array
          items:
            type: integer
            description: The ID of the fantasy team.
    """
    session = Session()

    # Query the league to get the league year
    league = session.query(League).filter(League.league_id == leagueId).first()
    
    if not league:
        session.close()
        return jsonify({"error": "League not found"}), 404

    # Define the maximum week for scoring
    max_week = 5

    # Query for the fantasy teams in the specified league
    fantasy_teams = session.query(FantasyTeam).filter(FantasyTeam.league_id == leagueId).all()

    result = []

    for team in fantasy_teams:
        # Get all the scores for the fantasy team up to week 5
        scores = session.query(FantasyScores).filter(
            FantasyScores.fantasy_team_id == team.fantasy_team_id,
            FantasyScores.week <= max_week
        ).order_by(FantasyScores.week.asc()).all()

        total_ranking_points = sum(score.rank_points for score in scores)
        
        result.append({
            "fantasy_team_id": team.fantasy_team_id,
            "total_ranking_points": total_ranking_points
        })

    # Sort by total ranking points
    result.sort(key=lambda x: x["total_ranking_points"], reverse=True)

    # Get the top 3 fantasy team IDs
    top_team_ids = [team["fantasy_team_id"] for team in result[:3]]

    session.close()

    return jsonify(top_team_ids)

@app.route('/api/leagues/<int:leagueId>/drafts', methods=['GET'])
def get_league_drafts(leagueId):
    """
    Retrieve all drafts in a league with their draft ID, round, and event key.
    ---
    tags:
      - Leagues
      - Drafts
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: ID of the league to retrieve drafts for.
    responses:
      200:
        description: A list of drafts with their ID, round, and event key.
        schema:
          type: array
          items:
            type: object
            properties:
              draft_id:
                type: integer
                description: The ID of the draft.
              rounds:
                type: integer
                description: The amound of rounds in the draft.
              event_key:
                type: string
                description: The event key for the draft.
      404:
        description: League not found.
    """
    session = Session()

    # Check if the league exists
    league = session.query(League).filter(League.league_id == leagueId).first()

    if not league:
        session.close()
        return jsonify({"error": "League not found"}), 404

    # Query for drafts associated with the league
    drafts = session.query(Draft).filter(Draft.league_id == leagueId).all()

    # Structure the response data
    result = [{
        "draft_id": draft.draft_id,
        "rounds": draft.rounds,
        "event_key": draft.event_key
    } for draft in drafts]

    session.close()

    return jsonify(result)

@app.route('/api/drafts/<int:draftId>/availableTeams', methods=['GET'])
def get_available_teams(draftId):
    """
    Retrieve all available teams for a specific draft, including their registered events and Statbotics data.
    ---
    tags:
      - Drafts
      - Teams
    parameters:
      - name: draftId
        in: path
        type: integer
        required: true
        description: ID of the draft to retrieve available teams for.
    responses:
      200:
        description: A list of available teams for the draft, including events and Statbotics data.
        schema:
          type: array
          items:
            type: object
            properties:
              team_number:
                type: integer
                description: The number of the available team.
              name:
                type: string
                description: The name of the team.
              events:
                type: array
                items:
                  type: object
                  properties:
                    event_key:
                      type: string
                      description: The key of the event.
                    week:
                      type: integer
                      description: The week of the event.
              year_end_epa:
                type: integer
                description: The year-end EPA from Statbotics data for the previous year.
      404:
        description: Draft not found
    """
    # Create a new session
    with Session() as session:
        # Retrieve the draft to ensure it exists
        draft = session.query(Draft).filter(Draft.draft_id == draftId).first()

        if draft is None:
            abort(404, description="Draft not found")

        # Determine if the league is FIM
        isFiM = draft.league.is_fim
        eventKey = draft.event_key
        year = draft.league.year
        previous_year = year - 1  # Calculate previous year

        # Base query
        base_query = None
        if isFiM:
          base_query = session.query(
              Team.team_number,
              Team.name,  # Add team name to the query
              FRCEvent.event_key,
              FRCEvent.week,
              StatboticsData.year_end_epa
          ).join(TeamScore, Team.team_number == TeamScore.team_key).join(
              FRCEvent, TeamScore.event_key == FRCEvent.event_key
          ).outerjoin(
              StatboticsData, (Team.team_number == StatboticsData.team_number) & (StatboticsData.year == previous_year)
          ).filter(
              FRCEvent.year == year,
              Team.team_number.notin_(
                  session.query(DraftPick.team_number).filter(
                      DraftPick.draft_id == draftId,
                      DraftPick.team_number != '-1'
                  )
              )
          )
        else:
            base_query = session.query(
              Team.team_number,
              Team.name,  # Add team name to the query
              FRCEvent.event_key,
              FRCEvent.week,
              StatboticsData.year_end_epa
          ).join(TeamScore, Team.team_number == TeamScore.team_key).join(
              FRCEvent, TeamScore.event_key == FRCEvent.event_key
          ).outerjoin(
              StatboticsData, (Team.team_number == StatboticsData.team_number) & (StatboticsData.year == year)
          ).filter(
              FRCEvent.year == year,
              TeamScore.event_key==eventKey,
              Team.team_number.notin_(
                  session.query(DraftPick.team_number).filter(
                      DraftPick.draft_id == draftId,
                      DraftPick.team_number != '-1'
                  )
              )
          )
        # Add condition for FIM
        if isFiM:
            base_query = base_query.filter(Team.is_fim == isFiM)

        # Execute the query and order by year_end_epa descending, with 0s coming last
        result = base_query.order_by(
            (StatboticsData.year_end_epa == 0).asc(),  # Place 0s last
            StatboticsData.year_end_epa.desc(),  # Sort by year_end_epa in descending order
            Team.team_number.asc()  # Sort by team_number in ascending order
        ).all()

        # Prepare the available teams list with events and Statbotics data
        available_teams = {}

        for row in result:
            team_number = row.team_number
            team_name = row.name  # Add the team name
            event_key = row.event_key
            week = row.week
            year_end_epa = row.year_end_epa if row.year_end_epa is not None else 0  # Set default value if None

            if team_number not in available_teams:
                available_teams[team_number] = {
                    "team_number": team_number,
                    "name": team_name,  # Include team name in the response
                    "events": [],
                    "year_end_epa": year_end_epa
                }

            available_teams[team_number]["events"].append({"event_key": event_key, "week": week})

        return jsonify(list(available_teams.values()))

@app.route('/api/drafts/<int:draftId>', methods=['GET'])
def get_draft_info(draftId):
    """
    Retrieve generic information for a specific draft.
    ---
    tags:
      - Drafts
    parameters:
      - name: draftId
        in: path
        type: integer
        required: true
        description: ID of the draft to retrieve information for.
    responses:
      200:
        description: The generic information of the draft.
        schema:
          type: object
          properties:
            draft_id:
              type: integer
              description: The unique identifier for the draft.
            league_id:
              type: integer
              description: The identifier of the league associated with the draft.
            event_key:
              type: integer
              description: The event key associated with the draft.
            discord_channel:
              type: string
              description: The Discord channel linked to the draft.
            rounds:
              type: integer
              description: The number of rounds in the draft.
      404:
        description: Draft not found
    """
    # Create a new session
    with Session() as session:
        # Retrieve the draft to ensure it exists
        draft = session.query(Draft).filter(Draft.draft_id == draftId).first()

        if draft is None:
            abort(404, description="Draft not found")

        # Prepare the response data
        draft_info = {
            "draft_id": draft.draft_id,
            "league_id": draft.league_id,
            "event_key": draft.event_key,
            "rounds": draft.rounds,
        }

        return jsonify(draft_info)

@app.route('/api/leagues/<int:leagueId>/availableTeams', methods=['GET'])
def get_available_teams_fim(leagueId):
    """
    Retrieve a list of available teams not on a fantasy team or on waivers,
    but are in FiM and registered for an event in the league's year.
    ---
    tags:
      - Leagues
      - Teams
    parameters:
      - name: leagueId
        in: path
        type: integer
        required: true
        description: The ID of the league for which to retrieve available teams.
    responses:
      200:
        description: A list of available teams for the specified league.
        schema:
          type: array
          items:
            type: object
            properties:
              team_number:
                type: integer
                description: The number of the available team.
              name:
                type: string
                description: The name of the team.
              events:
                type: array
                items:
                  type: object
                  properties:
                    event_key:
                      type: string
                      description: The key of the event.
                    week:
                      type: integer
                      description: The week of the event.
      404:
        description: League not found or no available teams.
    """
    # Create a new session
    with Session() as session:
        # Retrieve the league to ensure it exists
        league = session.query(League).filter(League.league_id == leagueId).first()

        if league is None:
            abort(404, description="League not found")

        if not league.is_fim:
            return jsonify([])

        year = league.year

        # Query to retrieve available teams
        available_teams_query = session.query(
            Team.team_number,
            Team.name,
            FRCEvent.event_key,
            FRCEvent.week,
        ).join(
            TeamScore, Team.team_number == TeamScore.team_key
        ).join(
            FRCEvent, TeamScore.event_key == FRCEvent.event_key
        ).outerjoin(
            TeamOwned, 
            and_(Team.team_number == TeamOwned.team_key, TeamOwned.league_id==leagueId)
        ).outerjoin(
            TeamOnWaivers, Team.team_number == TeamOnWaivers.team_number
        ).filter(
            TeamOwned.team_key.is_(None),  # Teams not on a fantasy team
            TeamOnWaivers.team_number.is_(None),  # Teams not on waivers
            FRCEvent.year == year,  # Teams registered for an event in the current year
            Team.is_fim.is_(True)  # Only FiM teams
        ).order_by(
            cast(Team.team_number, Integer).asc()  # Cast team_number to Integer for sorting
        ).all()

        # Prepare the available teams list
        available_teams = {}

        for row in available_teams_query:
            team_number = row.team_number
            team_name = row.name
            event_key = row.event_key
            week = row.week

            if team_number not in available_teams:
                available_teams[team_number] = {
                    "team_number": team_number,
                    "name": team_name,
                    "events": []
                }

            available_teams[team_number]["events"].append({"event_key": event_key, "week": week})

        # Return the list of available teams
        if not available_teams:
            return jsonify({"error": "No available teams found"}), 404

        return jsonify(list(available_teams.values()))

@app.route('/api/fimeventdata', methods=['GET'])
def get_fim_event_data():
    """
    Retrieve FiM event statistics
    ---
    tags:
      - FiM Event Data
    summary: Get event statistics for FiM events
    description: >
        Returns statistics for each FiM event, including the number of teams, maximum EPA, 8th and 24th highest EPA, 
        average EPA, and median EPA values.
    responses:
      200:
        description: A JSON array of event statistics
        content:
          application/json:
            schema:
              type: array
              items:
                type: object
                properties:
                  event_name:
                    type: string
                    description: The name of the event.
                    example: "FiM District Detroit Event"
                  teamcount:
                    type: integer
                    description: Number of teams in the event.
                    example: 40
                  maxepa:
                    type: number
                    format: float
                    description: Maximum EPA value for the event.
                    example: 85.4
                  top8epa:
                    type: number
                    format: float
                    description: The 8th highest EPA value for the event.
                    example: 75.3
                  top24epa:
                    type: number
                    format: float
                    description: The 24th highest EPA value for the event.
                    example: 60.2
                  avgepa:
                    type: number
                    format: float
                    description: Average EPA value for all teams in the event.
                    example: 50.7
                  medianepa:
                    type: number
                    format: float
                    description: Median EPA value for all teams in the event.
                    example: 55.1
      500:
        description: Error retrieving event data
        content:
          application/json:
            schema:
              type: object
              properties:
                error:
                  type: string
                  description: Error message.
                  example: "An error occurred while processing the request."
    """
    session = Session()
    try:
        # Query to retrieve event data
        subquery = (
            session.query(
                TeamScore.team_key.label('team'),
                TeamScore.event_key.label('event'),
                StatboticsData.year_end_epa.label('epa'),
                func.row_number().over(
                    partition_by=TeamScore.event_key,
                    order_by=StatboticsData.year_end_epa.desc()
                ).label('rank')
            )
            .join(StatboticsData, TeamScore.team_key == StatboticsData.team_number)
            .join(FRCEvent, TeamScore.event_key == FRCEvent.event_key)
            .filter(StatboticsData.year == 2024, FRCEvent.year == 2025)
            .subquery()
        )

        query = (
            session.query(
                FRCEvent.event_name,
                func.count(subquery.c.team).label('teamcount'),
                func.max(subquery.c.epa).label('maxepa'),
                func.max(case((subquery.c.rank == 8, subquery.c.epa), else_=None)).label('top8epa'),
                func.max(case((subquery.c.rank == 24, subquery.c.epa), else_=None)).label('top24epa'),
                func.avg(subquery.c.epa).label('avgepa'),
                func.percentile_cont(0.5).within_group(subquery.c.epa).label('medianepa')
            )
            .join(FRCEvent, FRCEvent.event_key == subquery.c.event)
            .group_by(FRCEvent.event_name)
            .order_by(func.avg(subquery.c.epa).desc())
        )

        results = [
            {
                'event_name': row.event_name,
                'teamcount': row.teamcount,
                'maxepa': row.maxepa,
                'top8epa': row.top8epa,
                'top24epa': row.top24epa,
                'avgepa': row.avgepa,
                'medianepa': row.medianepa
            }
            for row in query.all()
        ]

        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)  # Bind to all IPs
