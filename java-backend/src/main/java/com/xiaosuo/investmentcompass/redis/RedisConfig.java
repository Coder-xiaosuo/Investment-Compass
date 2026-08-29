package com.xiaosuo.investmentcompass.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;

/**
 * Redis 消息订阅配置
 * <p>
 * 配置 Redis 消息监听容器，订阅行情推送频道，
 * 将消息转发给 QuoteRedisSubscriber 处理。
 */
@Configuration
public class RedisConfig {

    /** 行情推送频道名称 */
    public static final String QUOTES_CHANNEL = "quotes";

    /**
     * 创建 Redis 消息监听容器
     * <p>
     * 监听 quotes 频道，收到消息后由 QuoteRedisSubscriber 转发到 WebSocket 会话。
     *
     * @param connectionFactory Redis 连接工厂
     * @param subscriber        行情消息订阅处理器
     * @return 消息监听容器
     */
    @Bean
    public RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            QuoteRedisSubscriber subscriber) {

        RedisMessageListenerContainer container = new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                new MessageListenerAdapter(subscriber),
                new ChannelTopic(QUOTES_CHANNEL));
        return container;
    }
}
