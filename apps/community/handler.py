import os
import json
import uuid

import aiofiles
from playhouse.shortcuts import model_to_dict

from TornadoForum.handler import RedisHandler
from apps.users.models import User
from apps.utils.auth_decorators import authenticated_async
from apps.community.forms import CommunityGroupForm, GroupApplyForm, PostForm, PostComentForm, CommentReplyForm
from apps.community.models import CommunityGroup, CommunityGroupMember, Post, PostComment, CommentLike
from apps.utils.utils_func import json_serial


class GroupHandler(RedisHandler):
    """小组列表和新增接口"""

    async def get(self, *args, **kwargs):

        re_data = []

        # 获得初步的SQL查询
        community_query = CommunityGroup.extend()

        # 根据类别过滤
        c = self.get_argument('c', None)
        if c:
            community_query = community_query.filter(CommunityGroup.category == c)

        # 根据参数排序
        order = self.get_argument('o', None)
        if order:
            if order == "new":
                community_query = community_query.order_by(CommunityGroup.add_time.desc())

            if order == "hot":
                community_query = community_query.order_by(CommunityGroup.member_nums.desc())

        # 返回指定数量
        limit = self.get_argument("limit", None)
        if limit:
            community_query = community_query.limit(int(limit))

        # 最终执行SQL查询 community_query 只是一个查询对象
        groups = await self.application.objects.execute(community_query)

        for group in groups:
            # 使用 model_to_dict 将查询的数据模型返回成字典
            group_dict = model_to_dict(group)

            # 返回完整的文件地址
            group_dict["front_image"] = f"{self.settings['SITE_URL']}/media/{group_dict['front_image']}/"
            re_data.append(group_dict)

        self.finish(json.dumps(re_data, default=json_serial))

    @authenticated_async
    async def post(self, *args, **kwargs):
        re_data = {}

        # 传输方式是表单提交不再是json格式
        community_form = CommunityGroupForm(self.request.body_arguments)

        if community_form.validate():
            # 这里我们自己校验文件传输 文件传输是在 request.files 中
            file_meta = self.request.files.get("front_image", None)

            if file_meta:
                # 文件存在的话就要设置保存 文件的读写和 socket 一样都是 IO 操作 因此这个地方我们需要异步操作

                for meta in file_meta:

                    # 为了防止重复文件名 保存的时候覆盖 为上传的文件重新命名
                    filename = meta["filename"]
                    new_filename = "{uuid}_{filename}".format(uuid=uuid.uuid1(), filename=filename)

                    # 设置文件上传路径
                    file_path = os.path.join(self.settings["MEDIA_ROOT"], new_filename)

                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(meta['body'])

                    group = await self.application.objects.create(CommunityGroup,
                                                                  add_user=self.current_user,
                                                                  name=community_form.name.data,
                                                                  category=community_form.category.data,
                                                                  desc=community_form.desc.data,
                                                                  notice=community_form.notice.data,
                                                                  front_image=new_filename)
                    re_data["id"] = group.id

            else:
                self.set_status(400)
                re_data["front_image"] = "请上传图片!"

        else:
            self.set_status(400)
            for field in community_form.errors:
                re_data[field] = community_form.errors[field][0]

        self.finish(re_data)


class GroupMemberHandler(RedisHandler):
    """小组加入接口"""

    @authenticated_async
    async def post(self, group_id, *args, **kwargs):
        """申请加入小组接口"""
        re_data = {}

        params = self.request.body.decode('utf-8')

        params = json.loads(params)

        applyform = GroupApplyForm.from_json(params)

        if applyform.validate():

            try:
                group = await self.application.objects.get(CommunityGroup, id=int(group_id))

                existed = await self.application.objects.get(CommunityGroupMember, community=group,
                                                             user=self.current_user)
                # 如果没有异常抛出 证明已经加入
                self.set_status(400)
                re_data["non_fields"] = "用户已经加入"

            except CommunityGroup.DoesNotExist as e:
                self.set_status(404)
                re_data["group"] = "小组不存在"

            except CommunityGroupMember.DoesNotExist as e:

                community_member = await self.application.objects.create(CommunityGroupMember,
                                                                         community=group,
                                                                         user=self.current_user,
                                                                         apply_reason=applyform.apply_reason.data)

                re_data["id"] = community_member.id

        else:

            self.set_status(400)
            for field in applyform.errors:
                re_data[field] = applyform.errors[field][0]

        self.finish(re_data)


class GroupDetailHanlder(RedisHandler):
    """获得小组详情接口"""

    @authenticated_async
    async def get(self, group_id, *args, **kwargs):
        re_data = {}
        try:
            group = await self.application.objects.get(CommunityGroup, id=int(group_id))

            re_data["name"] = group.name
            re_data["id"] = group.id
            re_data["desc"] = group.desc
            re_data["notice"] = group.notice
            re_data["member_nums"] = group.member_nums
            re_data["post_nums"] = group.post_nums
            re_data["front_image"] = "{}/media/{}/".format(self.settings["SITE_URL"], group.front_image)

        except CommunityGroup.DoesNotExist as e:
            self.set_status(404)

        self.finish(re_data)


class PostHandler(RedisHandler):
    """帖子相关接口"""

    @authenticated_async
    async def get(self, group_id, *args, **kwargs):
        post_list = []
        try:

            group = await self.application.objects.get(CommunityGroup, id=int(group_id))

            group_member = await self.application.objects.get(CommunityGroupMember, user=self.current_user,
                                                              community=group, status="agree")
            # 存在外键关联的时候需要进行 join 操作
            posts_query = Post.extend()

            c = self.get_argument("cate", None)
            if c == "hot":
                posts_query = posts_query.filter(Post.is_hot == True)
            if c == "excellent":
                posts_query = posts_query.filter(Post.is_excellent == True)

            posts = await self.application.objects.execute(posts_query)

            for post in posts:
                item_dict = {
                    "user": {
                        "id": post.user.id,
                        "nick_name": post.user.nick_name
                    },
                    "id": post.id,
                    "title": post.title,
                    "content": post.content,
                    "comment_nums": post.comment_nums
                }
                post_list.append(item_dict)
        except CommunityGroupMember.DoesNotExist as e:
            self.set_status(403)

        except CommunityGroup.DoesNotExist as e:
            self.set_status(404)

        self.finish(json.dumps(post_list))

    @authenticated_async
    async def post(self, group_id, *args, **kwargs):

        re_data = {}

        try:
            group = await self.application.objects.get(CommunityGroup, id=int(group_id))

            # 检查发帖的用户是否已经加入小组
            group_member = await self.application.objects.get(
                CommunityGroupMember, user=self.current_user, community=group, status="agree")

            param = self.request.body.decode("utf8")
            param = json.loads(param)
            form = PostForm.from_json(param)

            if form.validate():

                post = await self.application.objects.create(Post,
                                                             user=self.current_user,
                                                             title=form.title.data,
                                                             content=form.content.data,
                                                             group=group)
                re_data["id"] = post.id

            else:

                self.set_status(400)
                for field in form.errors:
                    re_data[field] = form.errors[field][0]

        except CommunityGroup.DoesNotExist as e:

            self.set_status(404)
            re_data["msg"] = "小组不存在"

        except CommunityGroupMember.DoesNotExist as e:

            self.set_status(403)
            re_data["msg"] = "你未加入到改小组"

        self.finish(re_data)


class PostDetailHandler(RedisHandler):
    @authenticated_async
    async def get(self, post_id, *args, **kwargs):
        """获取某一个帖子的详情"""
        re_data = {}

        post_details = await self.application.objects.execute(Post.extend().where(Post.id == int(post_id)))
        re_count = 0

        for data in post_details:
            item_dict = {}
            # 只对用户模型转换
            item_dict["user"] = model_to_dict(data.user)
            item_dict["title"] = data.title
            item_dict["content"] = data.content
            item_dict["comment_nums"] = data.comment_nums
            item_dict["add_time"] = data.add_time.strftime("%Y-%m-%d")
            re_data = item_dict

            re_count += 1

        if re_count == 0:
            self.set_status(404)

        self.finish(json.dumps(re_data, default=json_serial))


class PostCommentHanlder(RedisHandler):
    @authenticated_async
    async def get(self, post_id, *args, **kwargs):
        # 获取帖子的所有评论
        re_data = []

        try:
            post = await self.application.objects.get(Post, id=int(post_id))
            post_coments = await self.application.objects.execute(
                PostComment.extend().where(PostComment.post == post, PostComment.parent_comment.is_null(True)).order_by(
                    PostComment.add_time.desc())
            )

            for item in post_coments:
                has_liked = False
                try:
                    comments_like = await self.application.objects.get(CommentLike, post_comment_id=item.id,
                                                                       user_id=self.current_user.id)
                    has_liked = True
                except CommentLike.DoesNotExist:
                    pass

                item_dict = {
                    "user": model_to_dict(item.user),
                    "content": item.content,
                    "reply_nums": item.reply_nums,
                    "like_nums": item.like_nums,
                    "has_liked": has_liked,
                    "id": item.id,
                }

                re_data.append(item_dict)
        except Post.DoesNotExist as e:
            self.set_status(404)
        self.finish(json.dumps(re_data, default=json_serial))

    @authenticated_async
    async def post(self, post_id, *args, **kwargs):
        # 新增评论
        re_data = {}

        param = self.request.body.decode("utf8")
        param = json.loads(param)
        form = PostComentForm.from_json(param)

        if form.validate():
            try:
                post = await self.application.objects.get(Post, id=int(post_id))
                post_comment = await self.application.objects.create(PostComment, user=self.current_user, post=post,
                                                                     content=form.content.data)
                post.comment_nums += 1
                await self.application.objects.update(post)
                re_data["id"] = post_comment.id
                re_data["user"] = {}
                re_data["user"]["nick_name"] = self.current_user.nick_name
                re_data["user"]["id"] = self.current_user.id
            except Post.DoesNotExist as e:
                self.set_status(404)
        else:
            self.set_status(400)
            for field in form.errors:
                re_data[field] = form.errors[field][0]

        self.finish(re_data)


class CommentReplyHandler(RedisHandler):

    @authenticated_async
    async def get(self, comment_id, *args, **kwargs):
        """获得某个评论的回复"""

        re_data = []
        comment_replys = await self.application.objects.execute(
            PostComment.extend().where(PostComment.parent_comment_id == int(comment_id)))
        for item in comment_replys:
            item_dict = {
                "user": model_to_dict(item.user),
                "content": item.content,
                "reply_nums": item.reply_nums,
                "add_time": item.add_time.strftime("%Y-%m-%d"),
                "id": item.id
            }
            re_data.append(item_dict)
        self.finish(json.dumps(re_data, default=json_serial))

    @authenticated_async
    async def post(self, comment_id, *args, **kwargs):
        """提交评论的回复"""

        # 添加回复
        re_data = {}

        param = self.request.body.decode("utf8")
        param = json.loads(param)
        form = CommentReplyForm.from_json(param)

        if form.validate():
            try:
                comment = await self.application.objects.get(PostComment, id=int(comment_id))

                replyed_user = await self.application.objects.get(User, id=form.replyed_user.data)

                reply = await self.application.objects.create(PostComment,
                                                              user=self.current_user,
                                                              parent_comment=comment,
                                                              post_id=comment.post_id,
                                                              replyed_user=replyed_user,
                                                              content=form.content.data)
                # 更新comment的回复数
                comment.reply_nums += 1
                await self.application.objects.update(comment)

                re_data["id"] = reply.id
                re_data["user"] = {
                    "id": self.current_user.id,
                    "nick_name": self.current_user.nick_name
                }
            except PostComment.DoesNotExist as e:
                self.set_status(404)
            except User.DoesNotExist as e:
                self.set_status(400)
                re_data["replyed_user"] = "用户不存在"
        else:
            self.set_status(400)
            for field in form.errors:
                re_data[field] = form.errors[field][0]
        self.finish(re_data)


class CommentsLikeHanlder(RedisHandler):
    """点赞"""

    @authenticated_async
    async def post(self, comment_id, *args, **kwargs):
        re_data = {}
        try:
            comment = await self.application.objects.get(PostComment, id=int(comment_id))
            comment_like = await self.application.objects.create(CommentLike, user=self.current_user,
                                                                 post_comment=comment)
            # 更新评论数
            comment.like_nums += 1
            await self.application.objects.update(comment)

            re_data["id"] = comment_like.id

        except PostComment.DoesNotExist as e:
            self.set_status(404)

        self.finish(re_data)
