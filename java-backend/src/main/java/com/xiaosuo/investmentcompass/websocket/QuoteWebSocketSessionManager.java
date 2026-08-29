package com.xiaosuo.investmentcompass.websocket;

import com.google.gson.Gson;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * WebSocket 会话管理器
 * <p>
 * 管理所有 WebSocket 连接的生命周期和订阅关系。
 * 支持按会话注册/注销、按股票代码订阅/取消订阅、按订阅分发行情数据。
 */
@Slf4j
@Component
public class QuoteWebSocketSessionManager {

    /** 所有 WebSocket 会话，key=sessionId */
    private final ConcurrentHashMap<String, WebSocketSession> sessions = new ConcurrentHashMap<>();

    /** 各会话的订阅关系，key=sessionId，value=已订阅的股票代码集合 */
    private final ConcurrentHashMap<String, Set<String>> subscriptions = new ConcurrentHashMap<>();

    private final Gson gson = new Gson();

    /**
     * 注册新会话
     */
    public void register(WebSocketSession session) {
        sessions.put(session.getId(), session);
        subscriptions.put(session.getId(), ConcurrentHashMap.newKeySet());
    }

    /**
     * 注销会话
     */
    public void unregister(String sessionId) {
        sessions.remove(sessionId);
        subscriptions.remove(sessionId);
    }

    /**
     * 订阅指定股票代码的行情
     *
     * @param sessionId 会话ID
     * @param symbols   要订阅的股票代码集合
     */
    public void subscribe(String sessionId, Set<String> symbols) {
        Set<String> sub = subscriptions.get(sessionId);
        if (sub != null) {
            sub.addAll(symbols);
        }
    }

    /**
     * 取消订阅指定股票代码
     *
     * @param sessionId 会话ID
     * @param symbols   要取消订阅的股票代码集合
     */
    public void unsubscribe(String sessionId, Set<String> symbols) {
        Set<String> sub = subscriptions.get(sessionId);
        if (sub != null) {
            sub.removeAll(symbols);
        }
    }

    /**
     * 获取当前活跃会话数
     */
    public int getSessionCount() {
        return sessions.size();
    }

    /**
     * 广播消息到所有会话
     *
     * @param message 要广播的消息对象
     */
    public void broadcast(Object message) {
        String json = gson.toJson(Map.of("type", "quote", "data", message));
        TextMessage textMessage = new TextMessage(json);
        for (WebSocketSession session : sessions.values()) {
            if (session.isOpen()) {
                try {
                    session.sendMessage(textMessage);
                } catch (IOException e) {
                    log.warn("发送消息给 {} 失败: {}", session.getId(), e.getMessage());
                    unregister(session.getId());
                }
            } else {
                unregister(session.getId());
            }
        }
    }

    /**
     * 按订阅关系分发行情数据
     * <p>
     * 根据每个会话的订阅关系过滤行情数据，只推送该会话已订阅的股票行情。
     * 如果会话未设置订阅关系，则推送全部行情。
     *
     * @param quotes 行情数据列表
     */
    public void broadcastToSubscribed(List<Map<String, Object>> quotes) {
        if (sessions.isEmpty()) return;

        Map<String, List<Map<String, Object>>> perSession = new HashMap<>();

        for (Map.Entry<String, WebSocketSession> entry : sessions.entrySet()) {
            String sessionId = entry.getKey();
            Set<String> subscribedSymbols = subscriptions.get(sessionId);
            if (subscribedSymbols == null || subscribedSymbols.isEmpty()) {
                perSession.put(sessionId, quotes);
                continue;
            }
            List<Map<String, Object>> filtered = new ArrayList<>();
            for (Map<String, Object> q : quotes) {
                String sym = (String) q.get("symbol");
                if (subscribedSymbols.contains(sym)) {
                    filtered.add(q);
                }
            }
            if (!filtered.isEmpty()) {
                perSession.put(sessionId, filtered);
            }
        }

        for (Map.Entry<String, List<Map<String, Object>>> entry : perSession.entrySet()) {
            WebSocketSession session = sessions.get(entry.getKey());
            if (session == null || !session.isOpen()) continue;
            String json = gson.toJson(Map.of("type", "quote", "data", entry.getValue()));
            try {
                session.sendMessage(new TextMessage(json));
            } catch (IOException e) {
                log.warn("发送给 {} 失败: {}", entry.getKey(), e.getMessage());
                unregister(entry.getKey());
            }
        }
    }

    /**
     * 应用关闭时清理所有WebSocket会话
     */
    @PreDestroy
    public void closeAll() {
        for (WebSocketSession session : sessions.values()) {
            if (session.isOpen()) {
                try {
                    session.close();
                } catch (IOException e) {
                    log.warn("关闭会话 {} 失败: {}", session.getId(), e.getMessage());
                }
            }
        }
        sessions.clear();
        subscriptions.clear();
        log.info("所有 WebSocket 会话已关闭");
    }
}
