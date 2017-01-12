"""Add modularity properites to copr

Revision ID: 178a3754a9b9
Revises: 3b67c52f5277
Create Date: 2017-01-09 20:32:16.195039

"""

# revision identifiers, used by Alembic.
revision = '178a3754a9b9'
down_revision = '3b67c52f5277'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('copr', sa.Column('module_name', sa.String(length=100), nullable=True))
    op.add_column('copr', sa.Column('module_stream', sa.String(length=100), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('copr', 'module_stream')
    op.drop_column('copr', 'module_name')
    ### end Alembic commands ###
