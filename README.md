# **[Fantasy FIRST in Michigan](http://www.fantasyfim.com/)**

Welcome to **Fantasy FIRST in Michigan**! This application allows users to draft and manage fantasy teams based on real-world robotics competitions, providing real-time scoring, user rankings, and league management features.

## **Table of Contents**

1. [Overview](#overview)
2. [Features](#features)
3. [Technologies](#technologies)
4. [Installation](#installation)
5. [API Documentation](#api-documentation)
6. [Usage](#usage)
7. [Contributing](#contributing)
8. [License](#license)
9. [Contact](#contact)

---

## **Overview**

The Fantasy Robotics League App is a web platform where users can create leagues, draft robotics teams, and score them based on real-world performance in FIRST Robotics Competitions (FRC). Users can monitor team performance weekly, propose trades, and compete with friends for the top spot in their league. No user authentication is necessary, since the only write changes are done using the associated discord bot, which grabs the user ID given by the Discord webhook. The Discord bot facilitates all write operations, such as creating leagues, drafting teams, and proposing trades. These actions are synchronized with the web app, allowing users to track changes and view rankings without requiring login on the website.

## **Features**

- **League Management:** Create and join multiple leagues with custom rules.
- **Fantasy Draft:** Conduct live drafts to select teams from a pool of teams specific to the draft or league.
- **Trade System:** Propose and accept trades between teams.
- **Team Rankings:** View weekly and cumulative rankings based on team performance.
- **API Integration:** Data sourced from real FRC events, using [The Blue Alliance](https://www.thebluealliance.com/apidocs).

## **Technologies**

- **Backend:** Python (Flask, SQLAlchemy, Discord.py)
- **Frontend:** Vite, Tailwind, React Router
- **Database:** PostgreSQL
- **APIs:** Flask-based API for scores, teams, and rankings

## **Installation**

### **Prerequisites**

- Python 3.x
- Node.js
- PostgreSQL

### **Backend Setup**

1. Clone the repository:
   ```bash
   git clone https://github.com/anthonycgalea/fantasy-fim-discord-bot.git
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up the PostgreSQL database and configure environment variables in `.env`. Needed variables are given in .env.example

#### **API Setup**

4. Start the Flask server:
   ```bash
   flask run
   ```

#### **Discord bot Setup**

5. Start the discord bot:
    ```bash
    py main.py
    ```

### **Frontend Setup**

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install Node.js dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm start
   ```
4. Replace `frontend/public/IMG_0413.png` with your own image to customize the
   navbar logo.

### **Database Setup**

Make sure your PostgreSQL server is running, and apply migrations to set up the database schema:

```bash
flask db upgrade
```

## **API Documentation**

Production API documentation: [https://api.fantasyfim.com/apidocs/](https://api.fantasyfim.com/apidocs/).
Local documentation: [http://localhost:5000/apidocs/](http://localhost:5000/apidocs/).

All API routes live at the root of the API host. For example:

- `https://api.fantasyfim.com/currentWeek?year=2026`
- `https://api.fantasyfim.com/leagues`
- `https://api.fantasyfim.com/xp?teams=27,33&year=2026`
- `https://api.fantasyfim.com/drafts/1/availableTeams`

`GET /currentWeek` accepts an optional integer `year` query parameter. When supplied,
it returns the earliest active week in that year. When omitted, it retains the
existing behavior of returning the earliest active week across all years. Invalid
years return HTTP 400; no matching active week returns HTTP 404.

There is no `/api` prefix. Swagger JSON is served at
`https://api.fantasyfim.com/apidocs/swagger.json`.

### API hostname deployment

1. Point the `api.fantasyfim.com` DNS A/AAAA records to the API server.
2. Install [the Nginx server configuration](deploy/nginx/api.fantasyfim.com.conf).
   It forwards root paths unchanged to Gunicorn on `127.0.0.1:5000`, matching
   the existing deployment workflow.
3. Enable HTTPS for this hostname with a valid certificate (for example,
   using Certbot's Nginx integration), validate the Nginx configuration, and reload.
   The supplied server block is the initial HTTP configuration; TLS is configured
   on the server after certificate issuance.
4. Remove the old API proxy location from the website's server configuration and
   deploy the updated Flask application.
5. Update frontend API requests to use `https://api.fantasyfim.com` and remove
   their `/api` path prefix. The frontend source is maintained outside this repo.

These repository changes do not configure DNS, issue certificates, or modify
the live reverse proxy automatically.

## **Usage**

- After logging in with Discord, admins can create leagues and assign users to them.
- Draft teams from the FRC pool, and track your team's performance in real time.
- Propose trades, and view cumulative rankings for each league.
- Customize leagues with different scoring systems and team limits.

## **Contributing**

We welcome contributions! Please follow these steps to contribute:

1. Fork the repository.
2. Create a new branch:
   ```bash
   git checkout -b feature-name
   ```
3. Make your changes and commit them:
   ```bash
   git commit -m "Add new feature"
   ```
4. Push to the branch:
   ```bash
   git push origin feature-name
   ```
5. Create a pull request.

## **License**

This project is licensed under the GNU Public License v3. See the `LICENSE` file for details.

## **Contact**

For any questions or feedback, please reach out via Discord.
