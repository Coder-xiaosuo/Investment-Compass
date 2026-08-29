package com.xiaosuo.investmentcompass.config;

import com.xiaosuo.investmentcompass.websocket.QuoteWebSocketHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * WebSocket 配置
 * <p>
 * 注册实时行情 WebSocket 处理器，支持前端实时推送行情数据。
 */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final QuoteWebSocketHandler quoteWebSocketHandler;

    public WebSocketConfig(QuoteWebSocketHandler quoteWebSocketHandler) {
        this.quoteWebSocketHandler = quoteWebSocketHandler;
    }

    /**
     * 注册 WebSocket 处理器
     * <p>
     * 将 QuoteWebSocketHandler 注册到 /ws/quote 路径，
     * 允许所有来源的连接。
     */
    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(quoteWebSocketHandler, "/ws/quote")
                .setAllowedOrigins("*");
    }
}
