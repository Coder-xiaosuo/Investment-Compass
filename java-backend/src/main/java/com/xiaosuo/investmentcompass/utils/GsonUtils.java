package com.xiaosuo.investmentcompass.utils;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonSyntaxException;
import com.google.gson.reflect.TypeToken;
import lombok.extern.slf4j.Slf4j;

import java.lang.reflect.Type;

/**
 * Gson 工具类
 * 提供统一的 Gson 实例，避免重复创建
 *
 * @author xiaosuo
 */
@Slf4j
public class GsonUtils {

    /**
     * 单例 Gson 实例
     */
    private static final Gson GSON = new GsonBuilder()
            .create();

    private GsonUtils() {
        // 私有构造函数，防止实例化
    }

    /**
     * 获取 Gson 实例
     *
     * @return Gson 实例
     */
    public static Gson getInstance() {
        return GSON;
    }

    /**
     * 对象转 JSON 字符串
     *
     * @param obj 对象
     * @return JSON 字符串
     */
    public static String toJson(Object obj) {
        if (obj == null) {
            return null;
        }
        return GSON.toJson(obj);
    }

    /**
     * JSON 字符串转对象
     *
     * @param json  JSON 字符串
     * @param clazz 目标类型
     * @param <T>   泛型类型
     * @return 对象实例
     */
    public static <T> T fromJson(String json, Class<T> clazz) {
        if (json == null || json.isEmpty()) {
            return null;
        }
        return GSON.fromJson(json, clazz);
    }

    /**
     * JSON 字符串转对象（支持泛型）
     *
     * @param json      JSON 字符串
     * @param typeToken TypeToken 类型引用
     * @param <T>       泛型类型
     * @return 对象实例
     */
    public static <T> T fromJson(String json, TypeToken<T> typeToken) {
        if (json == null || json.isEmpty()) {
            return null;
        }
        return GSON.fromJson(json, typeToken.getType());
    }

    /**
     * JSON 字符串转对象（支持 Type）
     *
     * @param json JSON 字符串
     * @param type Type 类型
     * @param <T>  泛型类型
     * @return 对象实例
     */
    public static <T> T fromJson(String json, Type type) {
        if (json == null || json.isEmpty()) {
            return null;
        }
        return GSON.fromJson(json, type);
    }

    /**
     * 安全地将 JSON 字符串转为对象，解析失败时返回 null
     *
     * @param json  JSON 字符串
     * @param clazz 目标类型
     * @param <T>   泛型类型
     * @return 对象实例，解析失败返回 null
     */
    public static <T> T fromJsonSafe(String json, Class<T> clazz) {
        try {
            return fromJson(json, clazz);
        } catch (JsonSyntaxException e) {
            log.error("JSON 解析失败, json={}", json, e);
            return null;
        }
    }

    /**
     * 安全地将 JSON 字符串转为对象（支持泛型），解析失败时返回 null
     *
     * @param json      JSON 字符串
     * @param typeToken TypeToken 类型引用
     * @param <T>       泛型类型
     * @return 对象实例，解析失败返回 null
     */
    public static <T> T fromJsonSafe(String json, TypeToken<T> typeToken) {
        try {
            return fromJson(json, typeToken);
        } catch (JsonSyntaxException e) {
            log.error("JSON 解析失败, json={}", json, e);
            return null;
        }
    }
}
