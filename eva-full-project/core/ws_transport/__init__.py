"""Capture-backed chitchat.gg WebSocket transport.

Browser ছাড়াই session token দিয়ে chat — REST + Socket.IO ক্লায়েন্ট।
প্রোটোকল real captured frames থেকে বানানো (docs/CHITCHAT_PROTOCOL evidence)।
Browser mode-এর কোনো কিছু বদলায় না — শুধু session chat এই লেয়ার ব্যবহার করে।
"""
