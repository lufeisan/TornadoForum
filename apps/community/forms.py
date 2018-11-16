from wtforms_tornado import Form
from wtforms import StringField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Regexp, AnyOf, Length


class CommunityGroupForm(Form):
    name = StringField("名称", validators=[DataRequired("请输入小组名称")])
    category = StringField("类别", validators=[AnyOf(values=["DC宇宙", "漫威宇宙", "迪士尼宇宙", "其他宇宙"])])
    desc = TextAreaField("简介", validators=[DataRequired(message="请输入简介")])
    notice = TextAreaField("简介", validators=[DataRequired(message="请输入公告")])


class GroupApplyForm(Form):
    apply_reason = StringField("申请理由", validators=[DataRequired("请输入申请理由")])