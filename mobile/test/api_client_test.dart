import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/services/api_client.dart';
import 'package:mobile/services/storage_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late StorageService storageService;

  setUp(() {
    storageService = StorageService();
    ApiClient.setInstance(null);
  });

  test('ApiClient initial token save and refresh mechanism', () async {
    await storageService.saveTokens(
      accessToken: 'initial-access-token',
      refreshToken: 'initial-refresh-token',
    );

    final access = await storageService.getAccessToken();
    final refresh = await storageService.getRefreshToken();
    expect(access, 'initial-access-token');
    expect(refresh, 'initial-refresh-token');
  });

  test('ApiClient fallbackBaseUrls has appropriate defaults', () {
    expect(ApiClient.fallbackBaseUrls, isNotEmpty);
    expect(ApiClient.fallbackBaseUrls.first, contains('8000'));
  });

  test('ApiClient activeBaseUrl provides dynamic base URL and allows updates', () {
    expect(ApiClient.activeBaseUrl, equals(ApiClient.fallbackBaseUrls.first));
    ApiClient.activeBaseUrl = 'http://192.168.0.112:8000';
    expect(ApiClient.activeBaseUrl, equals('http://192.168.0.112:8000'));
    ApiClient.setInstance(null);
    expect(ApiClient.activeBaseUrl, equals(ApiClient.fallbackBaseUrls.first));
  });

  test('ApiClient handles force logout correctly', () async {
    await storageService.saveTokens(
      accessToken: 'token-to-be-cleared',
      refreshToken: 'refresh-to-be-cleared',
    );

    final client = ApiClient(storageService: storageService);
    bool forceLogoutBroadcasted = false;
    final sub = ApiClient.onForceLogout.stream.listen((_) {
      forceLogoutBroadcasted = true;
    });

    await client.handleForceLogout();

    expect(await storageService.getAccessToken(), isNull);
    expect(await storageService.getRefreshToken(), isNull);
    expect(forceLogoutBroadcasted, isTrue);

    await sub.cancel();
  });

  test('QueuedInterceptor retries failed 401 with refreshed token', () async {
    await storageService.saveTokens(
      accessToken: 'expired-token',
      refreshToken: 'valid-refresh-token',
    );

    final testDio = Dio(BaseOptions(baseUrl: 'http://test'));
    final refreshDio = Dio(BaseOptions(baseUrl: 'http://test'));
    final retryDio = Dio(BaseOptions(baseUrl: 'http://test'));
    int projectCallsCount = 0;
    int refreshCallsCount = 0;

    final mockInterceptor = InterceptorsWrapper(
      onRequest: (options, handler) {
        if (options.path == '/projects') {
          projectCallsCount++;
          final authHeader = options.headers['Authorization'];
          if (authHeader == 'Bearer expired-token') {
            return handler.reject(
              DioException(
                requestOptions: options,
                response: Response(
                  requestOptions: options,
                  statusCode: 401,
                  data: {'detail': 'Could not validate credentials: Token is expired'},
                ),
              ),
              true,
            );
          } else if (authHeader == 'Bearer new-refreshed-access-token') {
            return handler.resolve(
              Response(
                requestOptions: options,
                statusCode: 200,
                data: {'projects': []},
              ),
            );
          }
        } else if (options.path == '/auth/refresh') {
          refreshCallsCount++;
          return handler.resolve(
            Response(
              requestOptions: options,
              statusCode: 200,
              data: {
                'access_token': 'new-refreshed-access-token',
                'refresh_token': 'new-refreshed-refresh-token',
              },
            ),
          );
        }
        return handler.next(options);
      },
    );

    final client = ApiClient(
      dio: testDio,
      refreshDio: refreshDio,
      retryDio: retryDio,
      storageService: storageService,
    );

    testDio.interceptors.add(mockInterceptor);
    refreshDio.interceptors.add(mockInterceptor);
    retryDio.interceptors.add(mockInterceptor);

    // Call /projects with the expired token in storage
    final response = await client.dio.get(
      '/projects',
      options: Options(headers: {'Authorization': 'Bearer expired-token'}),
    );

    expect(response.statusCode, 200);
    expect(response.data, {'projects': []});
    expect(projectCallsCount, 2); // First failed with 401, second succeeded with 200
    expect(refreshCallsCount, 1);
    // Check that tokens were saved to storage together
    expect(await storageService.getAccessToken(), 'new-refreshed-access-token');
    expect(await storageService.getRefreshToken(), 'new-refreshed-refresh-token');
  });

  test('QueuedInterceptor handles in-flight refresh deduplication for concurrent 401s', () async {
    await storageService.saveTokens(
      accessToken: 'expired-token',
      refreshToken: 'valid-refresh-token',
    );

    final testDio = Dio(BaseOptions(baseUrl: 'http://test'));
    final refreshDio = Dio(BaseOptions(baseUrl: 'http://test'));
    final retryDio = Dio(BaseOptions(baseUrl: 'http://test'));
    int refreshCallsCount = 0;

    final mockInterceptor = InterceptorsWrapper(
      onRequest: (options, handler) async {
        if (options.path == '/auth/refresh') {
          refreshCallsCount++;
          // Simulate brief delay during refresh
          await Future.delayed(const Duration(milliseconds: 30));
          return handler.resolve(
            Response(
              requestOptions: options,
              statusCode: 200,
              data: {
                'access_token': 'fresh-token-xyz',
                'refresh_token': 'fresh-refresh-xyz',
              },
            ),
          );
        } else if (options.path.startsWith('/api-')) {
          final authHeader = options.headers['Authorization'];
          if (authHeader == 'Bearer expired-token') {
            return handler.reject(
              DioException(
                requestOptions: options,
                response: Response(
                  requestOptions: options,
                  statusCode: 401,
                  data: {'detail': 'Token is expired'},
                ),
              ),
              true,
            );
          } else if (authHeader == 'Bearer fresh-token-xyz') {
            return handler.resolve(
              Response(
                requestOptions: options,
                statusCode: 200,
                data: {'ok': true},
              ),
            );
          }
        }
        return handler.next(options);
      },
    );

    final client = ApiClient(
      dio: testDio,
      refreshDio: refreshDio,
      retryDio: retryDio,
      storageService: storageService,
    );

    testDio.interceptors.add(mockInterceptor);
    refreshDio.interceptors.add(mockInterceptor);
    retryDio.interceptors.add(mockInterceptor);

    // Fire 2 concurrent requests that both fail with 401
    final future1 = client.dio.get<dynamic>(
      '/api-1',
      options: Options(headers: {'Authorization': 'Bearer expired-token'}),
    );
    final future2 = client.dio.get<dynamic>(
      '/api-2',
      options: Options(headers: {'Authorization': 'Bearer expired-token'}),
    );

    final results = await Future.wait<Response<dynamic>>([future1, future2]);

    expect(results[0].statusCode, 200);
    expect(results[1].statusCode, 200);
    // Crucially: only 1 refresh call was made because the second one deduplicated!
    expect(refreshCallsCount, 1);
    expect(await storageService.getAccessToken(), 'fresh-token-xyz');
    expect(await storageService.getRefreshToken(), 'fresh-refresh-xyz');
  });

  test('QueuedInterceptor forces logout and clears tokens if refresh fails', () async {
    await storageService.saveTokens(
      accessToken: 'expired-token',
      refreshToken: 'dead-refresh-token',
    );

    final testDio = Dio(BaseOptions(baseUrl: 'http://test'));
    final refreshDio = Dio(BaseOptions(baseUrl: 'http://test'));
    final retryDio = Dio(BaseOptions(baseUrl: 'http://test'));
    bool forceLogoutTriggered = false;
    final sub = ApiClient.onForceLogout.stream.listen((_) {
      forceLogoutTriggered = true;
    });

    final mockInterceptor = InterceptorsWrapper(
      onRequest: (options, handler) {
        if (options.path == '/projects') {
          return handler.reject(
            DioException(
              requestOptions: options,
              response: Response(
                requestOptions: options,
                statusCode: 401,
                data: {'detail': 'Token is expired'},
              ),
            ),
            true,
          );
        } else if (options.path == '/auth/refresh') {
          // Refresh call itself fails with 401
          return handler.reject(
            DioException(
              requestOptions: options,
              response: Response(
                requestOptions: options,
                statusCode: 401,
                data: {'detail': 'INVALID_REFRESH_TOKEN'},
              ),
            ),
            true,
          );
        }
        return handler.next(options);
      },
    );

    final client = ApiClient(
      dio: testDio,
      refreshDio: refreshDio,
      retryDio: retryDio,
      storageService: storageService,
    );

    testDio.interceptors.add(mockInterceptor);
    refreshDio.interceptors.add(mockInterceptor);
    retryDio.interceptors.add(mockInterceptor);

    // Expect original request to throw DioException and trigger force logout
    await expectLater(
      client.dio.get(
        '/projects',
        options: Options(headers: {'Authorization': 'Bearer expired-token'}),
      ),
      throwsA(isA<DioException>()),
    );

    // Wait for async handler
    await Future.delayed(const Duration(milliseconds: 50));

    expect(forceLogoutTriggered, isTrue);
    expect(await storageService.getAccessToken(), isNull);
    expect(await storageService.getRefreshToken(), isNull);

    await sub.cancel();
  });
}
