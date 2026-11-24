# readme-2048

A shared 2048 game for my [GitHub profile](https://github.com/spiowm). Like in the monobank version, a game ends as soon as a 2048 tile appears.

GitHub READMEs can't run JavaScript, so the game is just an image and four links:

- `GET /board` returns the current board as an SVG with `Cache-Control: no-cache`, so GitHub's image proxy fetches a fresh copy on every page view.
- `GET /move/{left|up|down|right}` makes the move and redirects back to the profile.

The board lives in memory and is saved to SQLite after every move. The service keeps a per-player rate limit (player IDs are salted hashes of the IP address, raw IPs are not stored) and ignores known bots.

## Run

```bash
docker build -t readme-2048 .
docker run -p 8000:8000 -v readme-2048:/data -e PLAYER_SALT=change-me readme-2048
```

| Variable | Default | |
| --- | --- | --- |
| `PROFILE_URL` | `https://github.com/spiowm#make-a-move` | Where a move redirects |
| `PLAYER_SALT` | `dev-salt` | Secret for hashing player IPs |
| `STATS_TOKEN` | empty | Token for `GET /stats`, disabled when empty |
| `MIN_MOVE_INTERVAL` | `0.3` | Seconds between moves from one player |
