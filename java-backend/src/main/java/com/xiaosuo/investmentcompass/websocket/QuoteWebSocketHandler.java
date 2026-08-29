package com.xiaosuo.investmentcompass.websocket;

import com.google.gson.Gson;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.util.Map;
import java.util.Set;

/**
 * WebSocket 行情推送处理器
 * <p>
 * 处理实时行情 WebSocket 连接的生命周期和消息交互。
 * 支持订阅/取消订阅指定股票代码的行情数据，以及心跳检查。
 */
@Slf4j
@Component
public class QuoteWebSocketHandler extends TextWebSocketHandler {

    private final QuoteWebSocketSessionManager sessionManager;
    private final Gson gson = new Gson();

    public QuoteWebSocketHandler(QuoteWebSocketSessionManager sessionManager) {
        this.sessionManager = sessionManager;
    }

    /**
     * 连接建立时注册会话
     */
    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        sessionManager.register(session);
        log.info("WebSocket 已连接: {} (当前会话数: {})", session.getId(), sessionManager.getSessionCount());
    }

    /**
     * 处理客户端消息
     * <p>
     * 支持的消息类型：
     * - subscribe：订阅指定股票的行情推送
     * - unsubscribe：取消订阅指定股票
     * - ping：心跳检测，回应 pong
     */
    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> msg = gson.fromJson(message.getPayload(), Map.class);
            String type = (String) msg.get("type");
            if (type == null) return;

            switch (type) {
                case "subscribe" -> {
                    @SuppressWarnings("unchecked")
                    Set<String> symbols = gson.fromJson(gson.toJson(msg.get("symbols")), Set.class);
                    sessionManager.subscribe(session.getId(), symbols);
                    log.debug("已订阅 {}: {}", session.getId(), symbols);
                }
                case "unsubscribe" -> {
                    @SuppressWarnings("unchecked")
                    Set<String> symbols = gson.fromJson(gson.toJson(msg.get("symbols")), Set.class);
                    sessionManager.unsubscribe(session.getId(), symbols);
                }
                case "ping" -> {
                    session.sendMessage(new TextMessage("{\"type\":\"pong\"}"));
                }
                default -> log.warn("未知消息类型: {}", type);
            }
        } catch (Exception e) {
            log.warn("处理 WebSocket 消息失败: {}", e.getMessage());
        }
    }

    /**
     * 连接关闭时取消注册会话
     */
    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessionManager.unregister(session.getId());
        log.info("WebSocket 已断开: {} (当前会话数: {})", session.getId(), sessionManager.getSessionCount());
    }

    /**
     * 处理传输错误
     */
    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.warn("WebSocket 传输错误: {} - {}", session.getId(), exception.getMessage());
        sessionManager.unregister(session.getId());
    }
}
