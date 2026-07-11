import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Храним базу подключений и данные игроков
active_connections: List[WebSocket] = []
players_data: Dict[WebSocket, Dict[str, Any]] = {}

# Состояние игры
game_state = [""] * 9
current_turn = None  # Определится после кубика
winner = None
dice_value = None      
dice_roller = None     

# Список ролей: первые два занявших места — Игроки (1 и 2), остальные — Зрители
game_roles = ["Игрок 1", "Игрок 2"]

def check_winner(board):
    win_combinations = [[0, 1, 2], [3, 4, 5], [6, 7, 8],
                        [0, 3, 6], [1, 4, 7], [2, 5, 8],
                        [0, 4, 8], [2, 4, 6]
                       ]
    for combo in win_combinations:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != "":
            return board[combo[0]]
    if "" not in board:
        return "Ничья"
    return None

async def broadcast_lobby_status():
    """Рассылает всем список игроков, неопределившихся и занятые аватарки"""
    lobby_list = []
    for ws, data in players_data.items():
        lobby_list.append({
            "name": data["name"],
            "avatar": data["avatar"],
            "game_role": data["game_role"]
        })
    
    for connection in active_connections:
        await connection.send_json({
            "type": "lobby_update",
            "users": lobby_list
        })

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_turn, game_state, winner, dice_value, dice_roller
    
    await websocket.accept()
    active_connections.append(websocket)
    
    # Изначально зашедший — неопределившийся гость
    players_data[websocket] = {
        "name": "Аноним",
        "avatar": None,
        "game_role": "Неопределившийся"
    }
    
    # Отправляем начальное состояние игры
    await websocket.send_json({
        "type": "init", 
        "board": game_state, 
        "turn": current_turn,
        "winner": winner,
        "dice_value": dice_value,
        "dice_roller": dice_roller
    })
    
    await broadcast_lobby_status()

    try:
        while True:
            data = await websocket.receive_json()
            
            # Игрок сохраняет имя и выбирает аватарку
            if data["type"] == "join_lobby":
                name = data["name"] or f"Игрок {random.randint(100, 999)}"
                avatar = data["avatar"]
                
                # Проверяем, свободны ли места игроков
                assigned_roles = [p["game_role"] for p in players_data.values()]
                if "Игрок 1" not in assigned_roles:
                    role = "Игрок 1"
                elif "Игрок 2" not in assigned_roles:
                    role = "Игрок 2"
                else:
                    role = "Зритель 👀"
                
                players_data[websocket] = {
                    "name": name,
                    "avatar": avatar,
                    "game_role": role
                }
                
                # Отправляем личное подтверждение роли
                await websocket.send_json({"type": "role_assigned", "your_role": role})
                await broadcast_lobby_status()
            
            if data["type"] == "roll_dice":
                my_role = players_data[websocket]["game_role"]
                if my_role in ["Игрок 1", "Игрок 2"] and dice_value is None and winner is None:
                    dice_value = random.randint(1, 6)
                    dice_roller = players_data[websocket]["name"]
                    current_turn = "Игрок 1" if dice_value <= 3 else "Игрок 2"
                    
                    for connection in active_connections:
                        await connection.send_json({
                            "type": "dice_rolled",
                            "dice_value": dice_value,
                            "dice_roller": dice_roller,
                            "turn": current_turn
                        })

            if data["type"] == "move":
                my_role = players_data[websocket]["game_role"]
                index = data["index"]
                
                # Получаем аватарку текущего игрока для отрисовки на поле
                current_player_ws = [ws for ws, p in players_data.items() if p["game_role"] == current_turn]
                if current_player_ws:
                    avatar_to_place = players_data[current_player_ws[0]]["avatar"] or "❓"
                    
                    if current_turn is not None and game_state[index] == "" and my_role == current_turn and winner is None:
                        game_state[index] = avatar_to_place
                        
                        # Проверяем победу по аватарке
                        raw_winner = check_winner(game_state)
                        if raw_winner == "Ничья":
                            winner = "Ничья"
                        elif raw_winner is not None:
                            winner = players_data[websocket]["name"] # Запоминаем имя победителя
                        
                        if winner is None:
                            current_turn = "Игрок 2" if current_turn == "Игрок 1" else "Игрок 1"
                        
                        for connection in active_connections:
                            # Находим имя того, кто сейчас ходит, для статуса
                            next_turn_user = [p["name"] for p in players_data.values() if p["game_role"] == current_turn]
                            next_turn_name = next_turn_user[0] if next_turn_user else "???"
                            
                            await connection.send_json({
                                "type": "update",
                                "board": game_state,
                                "turn": current_turn,
                                "turn_name": next_turn_name,
                                "winner": winner
                            })
            
            if data["type"] == "reset":
                game_state = [""] * 9
                current_turn = None  
                winner = None
                dice_value = None
                dice_roller = None
                for connection in active_connections:
                    await connection.send_json({
                        "type": "init", 
                        "board": game_state, 
                        "turn": current_turn,
                        "winner": winner,
                        "dice_value": dice_value,
                        "dice_roller": dice_roller
                    })

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        if websocket in players_data:
            del players_data[websocket]
        await broadcast_lobby_status()
