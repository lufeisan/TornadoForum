import jwt
import functools

from apps.users.models import User


def authenticated_async(method):
    """在前后端分离的系统中 之前的登录装饰器 authenticated 不再实用"""
    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        # 从请求头中获取到 我们设置的 token
        tsessionid = self.request.headers.get("tsessionid", None)

        if tsessionid:
            # 对token过期进行异常捕捉
            try:

                # 从 token 中获得我们之前存进 payload 的用户id
                send_data = jwt.decode(tsessionid, self.settings["secret_key"], leeway=self.settings["jwt_expire"],
                                       options={"verify_exp": True})
                user_id = send_data["id"]

                # 从数据库中获取到user并设置给_current_user
                try:
                    user = await self.application.objects.get(User, id=user_id)

                    # 之所以赋值给  _current_user 是为了使用 self.current_user
                    # 通过 查看 authenticated 源码 我们知道 current_user 是一个动态属性
                    self._current_user = user

                    # 此处需要使用协程方式执行 因为需要装饰的是一个协程
                    await method(self, *args, **kwargs)

                except User.DoesNotExist as e:
                    self.set_status(401)
                    self.finish({
                        "msg": "用户不存在"
                    })

            except jwt.ExpiredSignatureError as e:
                self.set_status(401)
                self.finish({
                    "msg": "Token过期"
                })
        else:
            self.set_status(401)

            self.finish({
                "msg": "请传Token"
            })

    return wrapper
