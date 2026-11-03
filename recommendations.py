"""Parent preferences are separate from non-overridable eligibility policy."""
import json

RATINGS = ('E', 'E10+', 'T', 'M', 'UNRATED')

def suggested_defaults(age):
    """Suggestions only: caller must explicitly apply/save these settings."""
    if age is None:
        return {'show_prices':False,'show_budget':False,'show_links':False,
                'allowed_ratings':['E','E10+'], 'require_approval':True}
    ratings = ['E'] + (['E10+'] if age >= 10 else []) + (['T'] if age >= 13 else [])
    if age >= 17:
        ratings.append('M')
    return {'show_prices':age >= 10, 'show_budget':age >= 10, 'show_links':False,
            'allowed_ratings':ratings, 'require_approval':age < 13}


def permitted(product, profile):
    # Provider/regulatory/platform exclusions are not parents' content preferences.
    # Any nonempty unknown restriction fails closed. M ratings alone are NOT a
    # mandatory restriction: they can be explicitly allowed at any profile age.
    if product['mandatory_restriction']:
        return False
    categories = json.loads(profile['allowed_categories'])
    if categories is not None and product['category'] not in categories:
        return False
    if product['media_type'] == 'video_game':
        rating = product['content_rating'] or 'UNRATED'
        if rating not in json.loads(profile['allowed_ratings']):
            return False
        if not product['rating_verified'] and not profile['allow_unverified_games']:
            return False
    return True


def recommendation(product, profile):
    # Rank/label only; age does not determine eligibility.
    age, minimum = profile['child_age'], product['recommended_age_min']
    if not profile['use_age_recommendations'] or age is None or minimum is None:
        return 'Explore this idea'
    return 'Suggested for your interests' if age >= minimum else 'Outside your age suggestions · parent settings allow this'
