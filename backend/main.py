from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List

app = FastAPI()

# Список всех подключенных игроков (их сетевые соединения)
active_connections: List[WebSocket] = []

# Игровое поле: список из 9 пустых ячеек (индексы от 0 до 8)
game_state = [""] * 9
current_turn = "X"  # Начинают всегда крестики

@app.get("/")
def read_root():
    return {"status": "Сервер крестиков-ноликов успешно запущен!"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_turn, game_state
    
    await websocket.accept()
    active_connections.append(websocket)
    
    # Отправляем новому игроку текущее состояние доски
    await websocket.send_json({"type": "init", "board": game_state, "turn": current_turn})

    try:
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "move":
                index = data["index"]
                player = data["player"]
                
                # Проверка правил игры: клетка свободна и ходит тот, чей сейчас ход
                if game_state[index] == "" and player == current_turn:
                    game_state[index] = player
                    current_turn = "O" if current_turn == "X" else "X"
                    
                    # Рассылаем обновленное поле ВСЕМ игрокам
                    for connection in active_connections:
                        await connection.send_json({"type": "update", "board": game_state, "turn": current_turn})
            
            if data["type"] == "reset":
                game_state = [""] * 9
                current_turn = "X"
                for connection in active_connections:
                    await connection.send_json({"type": "init", "board": game_state, "turn": current_turn})

    except WebSocketDisconnect:
        active_connections.remove(websocket)