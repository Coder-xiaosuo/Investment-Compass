package com.xiaosuo.investmentcompass.redis;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.xiaosuo.investmentcompass.websocket.QuoteWebSocketSessionManager;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

import java.lang.reflect.Type;
import java.util.List;
import java.util.Map;

/**
 * Redis 行情消息订阅者
 * <p>
 * 监听 Redis 行情频道，收到行情推送后将数据通过 WebSocket 广播给已订阅的客户端。
 */
@Slf4j
@Component
public class QuoteRedisSubscriber implements MessageListener {

    private final QuoteWebSocketSessionManager sessionManager;
    private final Gson gson = new Gson();

    /** 行情列表 JSON 反序列化类型 */
    private static final Type QUOTE_LIST_TYPE = new TypeToken<List<Map<String, Object>>>() {}.getType();

    public QuoteRedisSubscriber(QuoteWebSocketSessionManager sessionManager) {
        this.sessionManager = sessionManager;
    }

    /**
     * 接收 Redis 消息并转发到 WebSocket
     * <p>
     * 将 Redis quotes 频道收到的行情数据解析后，按用户订阅分发到各 WebSocket 会话。
     */
    @Override
    public void onMessage(Message message, byte[] pattern) {
        try {
            String body = new String(message.getBody());
            List<Map<String, Object>> quotes = gson.fromJson(body, QUOTE_LIST_TYPE);
            if (quotes == null || quotes.isEmpty()) return;

            sessionManager.broadcastToSubscribed(quotes);
        } catch (Exception e) {
            log.warn("处理Redis行情消息失败: {}", e.getMessage());
        }
    }
}
