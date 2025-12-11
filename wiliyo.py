#!/usr/bin/env python3
import asyncio
import os
import sys
import json
import hashlib
import secrets
import time

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 6969
USER_DATA_FILE = "wiliyo_users.json"

clients = {}
online = set()
groups = {}
user_ips = {}

def load_users():
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_users(users):
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(users, f, indent=2)
    except:
        pass

users_db = load_users()

def hash_password(password):
    salt = secrets.token_hex(8)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{hashed}:{salt}"

def verify_password(stored_password, provided_password):
    if ":" not in stored_password:
        return False
    hashed, salt = stored_password.split(":")
    new_hash = hashlib.sha256((provided_password + salt).encode()).hexdigest()
    return new_hash == hashed

def clear(): 
    os.system('clear' if os.name == 'posix' else 'cls')

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    ip = addr[0]
    print(f"[SERVER] New connection from {ip}")
    
    try:
        # Send initial menu
        writer.write(b"\n=== WILIYO CHAT ===\n")
        await writer.drain()
        await asyncio.sleep(0.1)
        
        writer.write(b"1. Login\n2. Register\n\nChoice (1/2): ")
        await writer.drain()
        
        # Get choice
        try:
            choice_data = await asyncio.wait_for(reader.read(100), timeout=10.0)
            if not choice_data:
                print(f"[SERVER] No data from {ip}")
                writer.close()
                return
            choice = choice_data.decode('utf-8').strip()
        except asyncio.TimeoutError:
            print(f"[SERVER] Timeout from {ip}")
            writer.close()
            return
            
        print(f"[SERVER] User choice: {choice}")
        
        username = None
        
        if choice == "1":
            writer.write(b"\n--- LOGIN ---\nUsername: ")
            await writer.drain()
            
            try:
                username_data = await asyncio.wait_for(reader.read(100), timeout=10.0)
                username = username_data.decode('utf-8').strip()
            except asyncio.TimeoutError:
                writer.close()
                return
                
            print(f"[SERVER] Login attempt for: {username}")
            
            if username not in users_db:
                writer.write(b"User not found!\n")
                await writer.drain()
                writer.close()
                return
                
            writer.write(b"Password: ")
            await writer.drain()
            
            try:
                password_data = await asyncio.wait_for(reader.read(100), timeout=10.0)
                password = password_data.decode('utf-8').strip()
            except asyncio.TimeoutError:
                writer.close()
                return
            
            if not verify_password(users_db[username]["password"], password):
                writer.write(b"Wrong password!\n")
                await writer.drain()
                writer.close()
                return
                
            writer.write(b"\nLogin OK!\n")
            await writer.drain()
            
        elif choice == "2":
            writer.write(b"\n--- REGISTER ---\n")
            await writer.drain()
            
            while True:
                writer.write(b"Username: ")
                await writer.drain()
                
                try:
                    username_data = await asyncio.wait_for(reader.read(100), timeout=10.0)
                    username = username_data.decode('utf-8').strip()
                except asyncio.TimeoutError:
                    writer.close()
                    return
                
                if not username:
                    writer.write(b"Username required!\n")
                    continue
                    
                if username in users_db:
                    writer.write(b"Username taken! Try another.\n")
                    continue
                    
                break
            
            print(f"[SERVER] Registering user: {username}")
            
            writer.write(b"Password: ")
            await writer.drain()
            
            try:
                password_data = await asyncio.wait_for(reader.read(100), timeout=10.0)
                password = password_data.decode('utf-8').strip()
            except asyncio.TimeoutError:
                writer.close()
                return
            
            if not password:
                writer.write(b"Password required!\n")
                writer.close()
                return
            
            # Save user
            users_db[username] = {
                "password": hash_password(password),
                "created": time.strftime("%Y-%m-%d %H:%M"),
                "last_ip": ip
            }
            save_users(users_db)
            
            writer.write(b"\nRegistration OK!\n")
            await writer.drain()
            
        else:
            writer.write(b"Invalid choice!\n")
            await writer.drain()
            writer.close()
            return
        
        # Check if already online
        if username in online:
            writer.write(b"Already logged in!\n")
            await writer.drain()
            writer.close()
            return
            
        # Add to online users
        online.add(username)
        clients[writer] = username
        user_ips[username] = ip
        
        print(f"[SERVER] User {username} logged in from {ip}")
        
        # Send welcome
        welcome = f"\nWelcome {username}!\nOnline: {len(online)} users\nType /help\n\n"
        writer.write(welcome.encode())
        await writer.drain()
        
        # Notify others
        join_msg = f"[+] {username} joined"
        await broadcast(join_msg, exclude=writer)
        
        # Chat loop
        while True:
            try:
                data = await asyncio.wait_for(reader.read(1024), timeout=3600.0)
                if not data:
                    break
                    
                msg = data.decode('utf-8').strip()
                if not msg:
                    continue
                
                print(f"[CHAT] {username}: {msg[:50]}")
                
                # Commands
                if msg == "/help":
                    help_msg = "\nCommands:\n"
                    help_msg += "/help - This message\n"
                    help_msg += "/users - Online users\n"
                    help_msg += "/exit - Quit chat\n"
                    help_msg += "\nChat:\n"
                    help_msg += "@user message - Private\n"
                    help_msg += "#group message - Group\n"
                    help_msg += "message - Public\n"
                    writer.write(help_msg.encode())
                    await writer.drain()
                    
                elif msg == "/users":
                    if online:
                        users_msg = "\nOnline users:\n"
                        for user in sorted(online):
                            users_msg += f"- {user}\n"
                        users_msg += f"\nTotal: {len(online)}\n"
                    else:
                        users_msg = "\nNo users online\n"
                    writer.write(users_msg.encode())
                    await writer.drain()
                    
                elif msg == "/exit" or msg == "/quit":
                    writer.write(b"\nGoodbye!\n")
                    await writer.drain()
                    break
                    
                elif msg.startswith("@"):
                    parts = msg[1:].split(" ", 1)
                    target = parts[0]
                    text = parts[1] if len(parts) > 1 else ""
                    
                    if target == username:
                        writer.write(b"Cannot message yourself!\n")
                        await writer.drain()
                        continue
                    
                    sent = False
                    for w, u in clients.items():
                        if u == target:
                            w.write(f"\n[PM from {username}]: {text}\n".encode())
                            await w.drain()
                            sent = True
                    
                    if sent:
                        writer.write(f"Sent to @{target}\n".encode())
                    else:
                        writer.write(f"User @{target} not found\n".encode())
                    await writer.drain()
                    
                elif msg.startswith("#"):
                    parts = msg[1:].split(" ", 1)
                    group = parts[0]
                    text = parts[1] if len(parts) > 1 else ""
                    
                    if group not in groups:
                        groups[group] = set()
                    groups[group].add(username)
                    
                    # Send to all in group
                    for w, u in clients.items():
                        if u in groups[group] and u != username:
                            w.write(f"\n[#{group}] {username}: {text}\n".encode())
                            await w.drain()
                    
                    writer.write(f"Sent to #{group}\n".encode())
                    await writer.drain()
                    
                else:
                    # Public message
                    await broadcast(f"{username}: {msg}", exclude=writer)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[ERROR] {username}: {e}")
                break
                
    except Exception as e:
        print(f"[SERVER ERROR] {e}")
    finally:
        if writer in clients:
            user = clients[writer]
            online.discard(user)
            del clients[writer]
            print(f"[SERVER] {user} disconnected")
            
            # Notify others
            leave_msg = f"[-] {user} left"
            await broadcast(leave_msg)
            
        writer.close()

async def broadcast(msg, exclude=None):
    for writer in list(clients.keys()):
        if writer != exclude:
            try:
                writer.write(msg.encode() + b"\n")
                await writer.drain()
            except:
                pass

async def run_server():
    server = await asyncio.start_server(handle_client, SERVER_HOST, SERVER_PORT)
    addr = server.sockets[0].getsockname()
    
    clear()
    print(f"""
WILIYO CHAT SERVER v2.0
=======================

Server: {addr[0]}:{addr[1]}
Local: 192.168.0.100:{addr[1]}
Users: {len(users_db)} registered

Ready for connections...
""")
    
    async with server:
        await server.serve_forever()

async def run_client():
    clear()
    print("WILIYO CHAT CLIENT\n")
    
    server_ip = input("Server IP [192.168.0.100:6969]: ").strip()
    if not server_ip:
        server_ip = "192.168.0.100:6969"
    
    try:
        if ":" in server_ip:
            host, port = server_ip.split(":")
        else:
            host = server_ip
            port = 6969
        
        print(f"\nConnecting to {host}:{port}...")
        
        reader, writer = await asyncio.open_connection(host, int(port))
        print("Connected!\n")
        
    except Exception as e:
        print(f"Connection failed: {e}")
        return
    
    # Receive messages in background
    async def receiver():
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    print("\nServer disconnected")
                    break
                    
                msg = data.decode('utf-8', errors='ignore').rstrip()
                print("\r" + " " * 80 + "\r", end="")
                print(msg)
                print("> ", end="", flush=True)
        except:
            pass
    
    # Start receiver
    asyncio.create_task(receiver())
    
    try:
        # Handle authentication
        print("> ", end="", flush=True)
        
        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(None, input)
                if not user_input:
                    print("> ", end="", flush=True)
                    continue
                
                writer.write((user_input + "\n").encode())
                await writer.drain()
                
                if user_input in ["/exit", "/quit"]:
                    break
                    
                print("> ", end="", flush=True)
                
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except EOFError:
                break
                
    finally:
        writer.close()
        await writer.wait_closed()
        print("Disconnected")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        try:
            asyncio.run(run_server())
        except KeyboardInterrupt:
            print("\nServer stopped")
    else:
        try:
            asyncio.run(run_client())
        except KeyboardInterrupt:
            print("\nBye!")

if __name__ == "__main__":
    main()