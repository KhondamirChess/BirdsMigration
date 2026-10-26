from sklearn import datasets
import pandas as pd
iris = datasets.load_iris()

print(iris.keys())


# convert feature and label data to DataFrames
df_features = pd.DataFrame(iris.data, columns=iris.feature_names)
df_label = pd.DataFrame(iris.target, columns=['label'])
df_features.shape, df_label.shape  # check data sizes
print("----------------------")
print(df_features)
print("----------------------")
print(df_label)