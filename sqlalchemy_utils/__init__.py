from functools import wraps
from sqlalchemy.orm import defer
from sqlalchemy.orm.collections import InstrumentedList as _InstrumentedList
from sqlalchemy.orm.mapper import Mapper
from sqlalchemy.orm.query import _ColumnEntity
from sqlalchemy.orm.properties import ColumnProperty
from sqlalchemy.sql.expression import desc, asc


class InstrumentedList(_InstrumentedList):
    """Enhanced version of SQLAlchemy InstrumentedList. Provides some
    additional functionality."""

    def any(self, attr):
        return any(getattr(item, attr) for item in self)

    def all(self, attr):
        return all(getattr(item, attr) for item in self)


def instrumented_list(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return InstrumentedList([item for item in f(*args, **kwargs)])
    return wrapper


def sort_query(query, sort):
    """
    Applies an sql ORDER BY for given query. This function can be easily used
    with user-defined sorting.

    The examples use the following model definition:

        >>> import sqlalchemy as sa
        >>> from sqlalchemy import create_engine
        >>> from sqlalchemy.orm import sessionmaker
        >>> from sqlalchemy.ext.declarative import declarative_base
        >>> from sqlalchemy_utils import sort_query
        >>>
        >>>
        >>> engine = create_engine(
        ...     'sqlite:///'
        ... )
        >>> Base = declarative_base()
        >>> Session = sessionmaker(bind=engine)
        >>> session = Session()
        >>>
        >>> class Category(Base):
        ...     __tablename__ = 'category'
        ...     id = sa.Column(sa.Integer, primary_key=True)
        ...     name = sa.Column(sa.Unicode(255))
        >>>
        >>> class Article(Base):
        ...     __tablename__ = 'article'
        ...     id = sa.Column(sa.Integer, primary_key=True)
        ...     name = sa.Column(sa.Unicode(255))
        ...     category_id = sa.Column(sa.Integer, sa.ForeignKey(Category.id))
        ...
        ...     category = sa.orm.relationship(
        ...         Category, primaryjoin=category_id == Category.id
        ...     )



    1. Applying simple ascending sort

        >>> query = session.query(Article)
        >>> query = sort_query(query, 'name')

    2. Appying descending sort

        >>> query = sort_query(query, '-name')

    3. Applying sort to custom calculated label

        >>> query = session.query(
        ...     Category, db.func.count(Article.id).label('articles')
        ... )
        >>> query = sort_query(query, 'articles')

    4. Applying sort to joined table column

        >>> query = session.query(Article).join(Article.category)
        >>> query = sort_query(query, 'category-name')


    :param query: query to be modified
    :param sort: string that defines the label or column to sort the query by
    :param errors: whether or not to raise exceptions if unknown sort column
                   is passed
    """
    entities = [entity.entity_zero.class_ for entity in query._entities]
    for mapper in query._join_entities:
        if isinstance(mapper, Mapper):
            entities.append(mapper.class_)
        else:
            entities.append(mapper)

    # get all label names for queries such as:
    # db.session.query(Category, db.func.count(Article.id).label('articles'))
    labels = []
    for entity in query._entities:
        if isinstance(entity, _ColumnEntity) and entity._label_name:
            labels.append(entity._label_name)

    if not sort:
        return query

    if sort[0] == '-':
        func = desc
        sort = sort[1:]
    else:
        func = asc

    component = None
    parts = sort.split('-')
    if len(parts) > 1:
        component = parts[0]
        sort = parts[1]
    if sort in labels:
        return query.order_by(func(sort))

    for entity in entities:
        table = entity.__table__
        if component and table.name != component:
            continue
        if sort in table.columns:
            try:
                attr = getattr(entity, sort)
                query = query.order_by(func(attr))
            except AttributeError:
                pass
            break
    return query


def defer_except(query, columns):
    """
    Deferred loads all columns in given query, except the ones given.

    This function is very useful when working with models with myriad of
    columns and you want to deferred load many columns.

        >>> from sqlalchemy_utils import defer_except
        >>> query = session.query(Article)
        >>> query = defer_except(Article, [Article.id, Article.name])

    :param columns: columns not to deferred load
    """
    model = query._entities[0].entity_zero.class_
    fields = set(model._sa_class_manager.values())
    for field in fields:
        property_ = field.property
        if isinstance(property_, ColumnProperty):
            column = property_.columns[0]
            if column.name not in columns:
                query = query.options(defer(property_.key))
    return query


def escape_like(string, escape_char='*'):
    """
    Escapes the string paremeter used in SQL LIKE expressions

        >>> from sqlalchemy_utils import escape_like
        >>> query = session.query(User).filter(
        ...     User.name.ilike(escape_like('John'))
        ... )


    :param string: a string to escape
    :param escape_char: escape character
    """
    return (
        string
        .replace(escape_char, escape_char * 2)
        .replace('%', escape_char + '%')
        .replace('_', escape_char + '_')
    )
