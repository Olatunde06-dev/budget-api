# LEARN.md: how this back end works, and how to take it apart

You did not write this version line by line, so this guide is your map. Read the comments in
`main.py` first (they explain every section), then use this file to see how the pieces connect,
what to do when something breaks, and how to break things on purpose so you learn from it.

---

## 1. The whole project in one picture

```
 browser (static/index.html)
        |  1. sends the answers to an ADDRESS   e.g.  POST /submit
        v
   uvicorn            <- the program that stays switched on and listens
        |  2. hands the request to FastAPI
        v
   main.py  (app)     <- FastAPI looks up which function belongs to that address
        |  3. checks the data against the class (Person / Submission)
        |  4. make_estimate()  ->  budget_model.pkl   (your trained model)
        |  5. database.py      ->  submissions.db     (saves the answers)
        v
   JSON reply  ->  back to the browser, which draws the receipt

   later, on your laptop:   retrain.py reads submissions.db, trains again, and replaces budget_model.pkl
```

## 2. What each file is for

| File | Job | What breaks without it |
|---|---|---|
| `main.py` | The API: addresses, data checking, estimate | Nothing runs |
| `database.py` | Creates the table and saves/counts submissions | `/submit` and `/stats` fail |
| `budget_model.pkl` | Your trained model (you made this in the notebook) | The server refuses to start (`FileNotFoundError`) |
| `model_meta.json` | Notes about the model: typical miss (`mae`), version, algorithm | Server still runs, but uses a default miss of 12,000 |
| `static/index.html` | The form people see | `GET /` fails, the API still works |
| `retrain.py` | Retrains from real answers and swaps the model in if it is better | You can never improve the model |
| `test_api.py` | 14 checks that every address behaves | Nothing, but you lose your safety net |
| `requirements.txt` | The list of libraries a hosting service must install | The host cannot build your app |
| `submissions.db` | Created automatically. This is your collected data | Created again, empty |

## 3. Read `main.py` in this order

| Section (numbered in the file) | What it does | Try this to understand it |
|---|---|---|
| 1. File locations | Builds paths from `__file__` so the app works from any folder | Run uvicorn from another folder with `--app-dir` |
| 2. Loading the model | Loads the model once, reloads if the file changes | Replace the pkl while the server runs and watch `/health` |
| 3. The app | `app = FastAPI()`, plus CORS | Remove the CORS line and call the API from another origin |
| 4. The forms | `Person` and `Submission` classes: every rule about valid data | Send bad data to `/predict` in `/docs` |
| 5. `make_estimate` | Turns the form's words into the model's 7 columns and predicts | Change a key in the `row` dictionary |
| 6. The addresses | `@app.get` and `@app.post` connect addresses to functions | Add your own address (see section 8) |

## 4. Follow one submission, file by file

1. `index.html` collects the answers and sends `POST /submit` with JSON (function `post`).
2. FastAPI checks the JSON against `Submission` in `main.py`. Refused data stops here with a 422.
3. `submit()` runs and calls `make_estimate()`, which builds a one-row table and asks the model.
4. `submit()` calls `database.save_submission()`, which inserts a row in `submissions.db`.
5. `submit()` returns the estimate. The page draws the receipt and calls `/stats` to update the counter.
6. When enough people have submitted, `retrain.py` reads the same table back.

## 5. Commands (Windows PowerShell, inside the project folder)

| What | Command |
|---|---|
| Turn on the virtual environment | `.venv\Scripts\Activate.ps1` (you should see `(.venv)`) |
| Start the server | `uvicorn main:app --reload` |
| Open the page | `http://127.0.0.1:8000/` |
| Open the test page for every address | `http://127.0.0.1:8000/docs` |
| Stop the server | `Ctrl + C` in the terminal |
| Run the tests | `pip install httpx` (once), then `python test_api.py` |
| Retrain | `python retrain.py` (or `python retrain.py --min-people 30` while testing) |
| Save your exact library versions | `pip freeze > requirements.txt` |

`main:app` means "in the file `main.py`, run the thing called `app`". `--reload` restarts the server
each time you save a file. It is for development only.

## 6. When something breaks

**Always read the LAST line of the error first.** It says what went wrong. The lines above it show
where. The real error for a web request is in the **terminal**, not in the browser.

| What you see | What it means | What to do |
|---|---|---|
| `ModuleNotFoundError: No module named 'x'` | Python cannot find that library | Check the spelling (you hit `pydandtic` once). Check `(.venv)` is showing. Then `pip install x` |
| `NameError: name 'BaseModel' is not defined` | You used a name you never imported | Add the `from ... import ...` line |
| `InconsistentVersionWarning` | The model was saved with another scikit-learn version | `pip install scikit-learn==VERSION`, using the version in the warning |
| `GET /favicon.ico 404` | Browsers ask for a tab icon | Ignore it |
| `422 Unprocessable Entity` | The data did not fit the class | Read `detail`: `loc` names the field, `msg` says why |
| `500 Internal Server Error` | A bug in your own function | Read the traceback in the terminal |
| `Error loading ASGI app. Could not import module "main"` | uvicorn cannot find `main.py` | `cd` into the project folder first |
| `Address already in use` | A server is already running on that port | Stop the old one (`Ctrl + C`) or use `--port 8001` |
| `FileNotFoundError: budget_model.pkl` | The model file is not in this folder | Copy it in |
| `The feature names should match those that were passed during fit` | The columns sent to the model differ from the ones it trained on | Compare `/model-info` with the `row` in `make_estimate` |
| `sqlite3.OperationalError: no such table` | The table was never created | `database.init_db()` must run at start-up |
| Browser console: `Failed to fetch` or `blocked by CORS` | The page cannot reach the API | Is the server running? Is the address right? Use `?api=http://127.0.0.1:8000` if the page comes from another tool |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | PowerShell blocks scripts | Use Command Prompt, or run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |

## 7. Break it on purpose (do one, read the error, then undo it)

1. **Delete the line `from pydantic import BaseModel`.** Save. The server fails at start-up. Which line does the error point to?
2. **In `/docs`, send `age: 10` to `/predict`.** Read the 422. Then change `ge=18` to `ge=5` in `Person`, save, and send it again.
3. **Change `"age"` to `"ages"` in the `row` dictionary** inside `make_estimate`. Send a valid request. You get a 500 with a message. Where does that message come from?
4. **Delete `submissions.db` and remove the `database.init_db()` line.** Restart and press submit on the page. Read the error, then put the line back.
5. **Rename the `static` folder.** Open `/`. What happens, and does `/health` still work? Why?
6. **Set `allow_origins=[]`** in the CORS line, open the page with Live Server using `?api=http://127.0.0.1:8000`, and read the error in the browser console.
7. **Replace `budget_model.pkl` while the server is running** (copy your backup over it) and watch `/health` and `/model-info`.

## 8. Add something yourself (the best way to learn)

- Add `@app.get("/version")` that returns the model version. Four lines.
- Add a field `city: str` to `Person` and see which parts of the project must change (the page, the database, retrain.py).
- Write one more check in `test_api.py`.

## 9. Before you put it online

- **The host must run:** `uvicorn main:app --host 0.0.0.0 --port $PORT` (no `--reload`). Check your host's docs for how it sets the port.
- **Versions:** run `pip freeze > requirements.txt` in your virtual environment. Keep `scikit-learn` at the version the `.pkl` was saved with.
- **The database file can disappear.** Many free hosting plans wipe the disk when the app restarts or redeploys. Check your host's terms. If the disk is temporary, either attach a persistent disk and set `DATABASE_PATH` to it, or move to a hosted database. Losing the data you collected would be the worst outcome, so settle this before you share the link.
- **CORS:** replace `"*"` with your site's address.
- **Privacy:** never commit `submissions.db` to GitHub (the `.gitignore` already blocks it). Nobody can download the data through the API, because `/stats` returns only a count, so keep it that way.
- **There is no login and no rate limit.** Anyone with the link can submit. That is fine for friends, but add limits before a wide launch.

## 10. What to learn next

Tests with `pytest`, logging, login for an admin address, PostgreSQL instead of SQLite, Docker.
